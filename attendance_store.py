"""Yoklama oturumunu bellekte ve JSON dosyasında birlikte tutar.

Değişiklikler önce bir kopyaya uygulanır. Dosya yazılamazsa bellekteki yoklama da
değişmez. Bu depo, aynı dizini kullanan tek bir sunucu işlemi için tasarlanmıştır.
"""

import copy
import json
import os
import re
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from uuid import uuid4


def validate_roster(students):
    """Öğrenci numaralarını ve adları doğrula; yalnız bu iki alanı geri döndür."""
    if not isinstance(students, list):
        raise ValueError("Öğrenci listesi JSON dizisi olmalıdır.")
    roster = []
    seen = set()
    for student in students:
        if not isinstance(student, dict):
            raise ValueError("Her öğrenci bir JSON nesnesi olmalıdır.")
        student_id = student.get("id")
        name = student.get("name")
        if not isinstance(student_id, str) or not re.fullmatch(r"[0-9]{1,64}", student_id):
            raise ValueError("Öğrenci numarası 1–64 rakam içeren bir metin olmalıdır.")
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise ValueError("Öğrenci adı 1–200 karakter olmalıdır.")
        if student_id in seen:
            raise ValueError("Öğrenci numaraları benzersiz olmalıdır.")
        seen.add(student_id)
        roster.append({"id": student_id, "name": name.strip()})
    return roster


def atomic_json(path, data):
    """Önce geçici dosyaya yaz, tamamlanınca eski dosyanın yerine geçir."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, suffix=".pending", delete=False
        ) as stream:
            pending = stream.name
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, path)
        pending = None
    finally:
        if pending and os.path.exists(pending):
            os.unlink(pending)


class AttendanceStore:
    """Manuel işaretleme, yüz tanıma ve arşiv işlemlerinin ortak kayıt noktası."""

    def __init__(self, data_dir, roster):
        self.data_dir = Path(data_dir)
        self.current_path = self.data_dir / "current.json"
        self.records_dir = self.data_dir / "records"
        self.lock = threading.RLock()
        roster = validate_roster(roster)
        if self.current_path.exists():
            try:
                state = json.loads(self.current_path.read_text(encoding="utf-8"))
                self._validate_state(state)
            except (ValueError, KeyError, TypeError) as exc:
                raise RuntimeError(
                    "current.json geçersiz; korunmuştur. Dosyayı inceleyin veya yedekten geri alın."
                ) from exc
            self.state = state
            self.sync_roster(roster)
        else:
            self.state = self._new_state(roster)
            atomic_json(self.current_path, self.state)

    @staticmethod
    def _empty_attendance(student):
        return {
            **student,
            "status": "absent",
            "time": None,
            "auto": False,
            "manual_override": False,
        }

    @classmethod
    def _new_state(cls, roster):
        now = datetime.now()
        return {
            "schema_version": 1,
            "date": now.strftime("%Y-%m-%d"),
            "started_at": now.strftime("%H:%M:%S"),
            "generation": uuid4().hex,
            "students": {student["id"]: cls._empty_attendance(student) for student in roster},
        }

    @staticmethod
    def _validate_state(state):
        if not isinstance(state, dict) or state.get("schema_version") != 1:
            raise ValueError("Desteklenmeyen kayıt sürümü")
        datetime.strptime(state["date"], "%Y-%m-%d")
        datetime.strptime(state["started_at"], "%H:%M:%S")
        if not isinstance(state["generation"], str) or not state["generation"]:
            raise ValueError("Oturum kimliği eksik")
        students = state["students"]
        if not isinstance(students, dict):
            raise ValueError("Geçersiz öğrenci kaydı")
        validate_roster(list(students.values()))
        for sid, student in students.items():
            if sid != student["id"] or student.get("status") not in ("present", "absent"):
                raise ValueError("Geçersiz yoklama durumu")
            if not isinstance(student.get("auto"), bool):
                raise ValueError("Geçersiz işaretleme kaynağı")
            if not isinstance(student.get("manual_override", False), bool):
                raise ValueError("Geçersiz manuel durum")
            student.setdefault("manual_override", False)
            if student.get("time") is not None:
                datetime.strptime(student["time"], "%H:%M:%S")

    def _commit(self, state):
        # Yazma sırası önemli: disk hatası varsa eski bellek durumu korunmalı.
        atomic_json(self.current_path, state)
        self.state = state

    def snapshot(self):
        """Ekran ve rapor için bağımsız bir kopya ve yoklama sayıları hazırla."""
        with self.lock:
            state = copy.deepcopy(self.state)
        students = sorted(
            state["students"].values(),
            key=lambda s: (s["status"] != "present", s["name"].casefold(), s["id"]),
        )
        present = sum(s["status"] == "present" for s in students)
        total = len(students)
        state["students"] = students
        state["stats"] = {
            "total": total,
            "present": present,
            "absent": total - present,
            "rate": round(present / total * 100, 1) if total else 0,
        }
        return state

    def sync_roster(self, roster):
        """Adları ve yeni öğrencileri al; oturumdaki eski işaretlemeleri koru."""
        roster = validate_roster(roster)
        with self.lock:
            state = copy.deepcopy(self.state)
            for student in roster:
                student_id = student["id"]
                if student_id in state["students"]:
                    state["students"][student_id]["name"] = student["name"]
                else:
                    state["students"][student_id] = self._empty_attendance(student)
            # Eski listeye göre işlenmekte olan kamera karelerini geçersiz kılar.
            state["generation"] = uuid4().hex
            self._commit(state)

    def toggle(self, student_id):
        """Var/yok durumunu değiştir; bu oturumda manuel kararı öncelikli tut."""
        with self.lock:
            if student_id not in self.state["students"]:
                raise KeyError(student_id)
            state = copy.deepcopy(self.state)
            student = state["students"][student_id]
            present = student["status"] != "present"
            student.update(
                status="present" if present else "absent",
                time=datetime.now().strftime("%H:%M:%S") if present else None,
                auto=False,
                manual_override=True,
            )
            self._commit(state)
            return copy.deepcopy(student)

    def mark_recognized(self, faces, generation):
        """Eşleşenleri var yap. Oturum değişmişse kareyi uygulamadan None döndür."""
        with self.lock:
            if generation != self.state["generation"]:
                return None
            state = copy.deepcopy(self.state)
            newly_marked = []
            for face in faces:
                student = state["students"].get(face.get("id"))
                if not face.get("matched") or student is None:
                    continue
                if student["status"] == "present" or student["manual_override"]:
                    continue
                student.update(
                    status="present", time=datetime.now().strftime("%H:%M:%S"), auto=True
                )
                newly_marked.append(student["name"])
            if newly_marked:
                self._commit(state)
            return newly_marked

    def save(self):
        """Mevcut oturumu benzersiz bir arşiv dosyasına kopyala."""
        with self.lock:
            data = self.snapshot()
            data["saved_at"] = datetime.now().isoformat(timespec="seconds")
            filename = f"yoklama_{datetime.now():%Y%m%d_%H%M%S_%f}_{uuid4().hex[:8]}.json"
            atomic_json(self.records_dir / filename, data)
            return filename

    def reset(self, roster):
        """Önce arşivle, ardından yeni oturumu aç. Arşiv hatasında sıfırlama yapma."""
        roster = validate_roster(roster)
        with self.lock:
            filename = self.save()
            self._commit(self._new_state(roster))
            return filename
