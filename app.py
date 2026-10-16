"""YoklamaX'in HTTP rotaları ve yerel sunucu başlangıcı.

Okuma sırası: create_app ayarları ve depoyu hazırlar; rotalar istekleri ilgili
modüle iletir; main sunucuyu açar. Sadece import etmek model veya sunucu başlatmaz.
"""

import argparse
import base64
import binascii
import io
import json
import logging
import os
import secrets
import sys
import threading
import warnings
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import cv2
import numpy as np
from flask import Flask, jsonify, render_template, request, send_file, send_from_directory, session
from PIL import Image, UnidentifiedImageError
from werkzeug.exceptions import BadRequest, HTTPException

from attendance_store import AttendanceStore, validate_roster
from face_manager import FaceManager, FaceRecognitionError, FaceRecognitionUnavailable
from pdf_generator import generate_pdf

BASE_DIR = Path(__file__).resolve().parent
MAX_REQUEST_BYTES = 6 * 1024 * 1024
MAX_IMAGE_BYTES = 4 * 1024 * 1024
RECOGNITION_WIDTH = 640
MATCH_TOLERANCE = 0.35
DEMO_STUDENTS = [
    {"id": "10001", "name": "Örnek Öğrenci Ada"},
    {"id": "10002", "name": "Örnek Öğrenci Deniz"},
    {"id": "10003", "name": "Örnek Öğrenci Ege"},
]


def _resolve_path(value):
    path = Path(value)
    return path if path.is_absolute() else BASE_DIR / path


def _json_body():
    """POST rotalarının beklediği JSON nesnesini al veya 400 hatası ver."""
    if not request.is_json:
        raise BadRequest("JSON gövdesi gereklidir.")
    data = request.get_json()
    if not isinstance(data, dict):
        raise BadRequest("JSON nesnesi gereklidir.")
    return data


def decode_image(value):
    """Tarayıcıdan gelen base64 verisini sınırlı boyutlu bir OpenCV karesine çevir."""
    if not isinstance(value, str) or not value or len(value) > MAX_REQUEST_BYTES:
        raise BadRequest("Görüntü verisi eksik veya çok büyük.")
    if value.startswith("data:"):
        prefix, separator, value = value.partition(",")
        if not separator or prefix not in {
            "data:image/jpeg;base64",
            "data:image/png;base64",
            "data:image/webp;base64",
            "data:image/bmp;base64",
        }:
            raise BadRequest("Desteklenmeyen görüntü biçimi.")
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise BadRequest("Geçersiz base64 görüntü verisi.") from exc
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise BadRequest("Görüntü boş veya çok büyük.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw), formats=["JPEG", "PNG", "WEBP", "BMP"]) as image:
                width, height = image.size
                if (
                    min(width, height) < 2
                    or max(width, height) > 4096
                    or width * height > 8_000_000
                ):
                    raise BadRequest(
                        "Görüntü boyutu 2–4096 piksel ve en fazla 8 megapiksel olmalıdır."
                    )
                image.load()
                return cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2BGR)
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
    ) as exc:
        raise BadRequest("Görüntü çözümlenemedi.") from exc


def recognize_frame(manager, frame):
    """Hesabı küçük karede yap; yüz kutularını asıl görüntü boyutuna geri taşı."""
    height, width = frame.shape[:2]
    scale = min(1.0, RECOGNITION_WIDTH / max(width, height))
    small = cv2.resize(frame, (max(2, round(width * scale)), max(2, round(height * scale))))
    faces = manager.recognize(small, tolerance=MATCH_TOLERANCE)
    for face in faces:
        box = face["box"]
        for key in ("top", "bottom"):
            box[key] = round(box[key] * height / small.shape[0])
        for key in ("left", "right"):
            box[key] = round(box[key] * width / small.shape[1])
    return faces


def reference_photo_path(directory, filename):
    """Yalnız referans klasöründeki bir görüntü dosyasının yolunu kabul et."""
    if not isinstance(filename, str) or Path(filename).name != filename:
        return None
    if Path(filename).suffix.lower() not in FaceManager.SUPPORTED_EXTENSIONS:
        return None
    directory = directory.resolve()
    path = (directory / filename).resolve()
    if not path.is_relative_to(directory) or not path.is_file():
        return None
    return path


def create_app(config=None, face_manager=None):
    """Uygulamayı kur. Testler kendi ayarlarını ve sahte yüz yöneticisini verebilir."""
    app = Flask(__name__, template_folder=str(BASE_DIR), static_folder=None)
    demo = os.getenv("YOKLAMAX_DEMO", "0") == "1"
    app.config.update(
        SECRET_KEY=os.getenv("YOKLAMAX_SECRET_KEY") or secrets.token_hex(32),
        MODE=os.getenv("YOKLAMAX_MODE", "recognition"),
        DEMO=demo,
        DATA_DIR=os.getenv(
            "YOKLAMAX_DATA_DIR", str(BASE_DIR / "data" / ("demo" if demo else "live"))
        ),
        FACES_DIR=os.getenv("YOKLAMAX_FACES_DIR", str(BASE_DIR / "faces")),
        MAX_CONTENT_LENGTH=MAX_REQUEST_BYTES,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        TRUSTED_HOSTS=["localhost", "127.0.0.1", "[::1]"],
    )
    app.config.update(config or {})
    if app.config["DEMO"]:
        app.config["MODE"] = "manual"
    if app.config["MODE"] not in ("manual", "recognition"):
        raise ValueError("YOKLAMAX_MODE manual veya recognition olmalıdır.")
    data_dir = _resolve_path(app.config["DATA_DIR"])
    faces_dir = _resolve_path(app.config["FACES_DIR"])
    manager = face_manager or FaceManager(faces_dir=str(faces_dir))

    def current_roster():
        """Çalışma moduna göre öğrenci listesinin tek kaynağını seç."""
        if app.config["DEMO"]:
            return [dict(s) for s in DEMO_STUDENTS]
        if app.config["MODE"] == "manual":
            path = data_dir / "students.json"
            if not path.exists():
                return []
            return validate_roster(json.loads(path.read_text(encoding="utf-8")))
        return validate_roster(manager.get_all_students())

    if app.config["MODE"] == "recognition":
        manager.load_faces()
    store = AttendanceStore(data_dir, current_roster())
    app.extensions["attendance_store"] = store
    app.extensions["face_manager"] = manager
    recognition_lock = threading.Lock()
    reload_lock = threading.Lock()

    def recognition_status():
        if app.config["MODE"] == "manual":
            return {"available": False, "loaded_count": 0, "skipped": [], "error": None}
        if hasattr(manager, "status"):
            return manager.status()
        return {
            "available": True,
            "loaded_count": manager.get_student_count(),
            "skipped": [],
            "error": None,
        }

    def attendance_payload():
        snapshot = store.snapshot()
        filenames = {s["id"]: s.get("filename") for s in manager.get_all_students()}
        for student in snapshot["students"]:
            if reference_photo_path(faces_dir, filenames.get(student["id"])):
                student["photo_url"] = f"/api/students/{student['id']}/photo"
        return snapshot

    @app.before_request
    def local_request_guard():
        # Host kontrolü, dış bir sitenin yerel öğrenci verilerini okumasını da önler.
        if urlsplit(request.host_url).hostname not in ("localhost", "127.0.0.1", "::1"):
            return jsonify(error="Yalnızca yerel erişim desteklenir."), 400
        if request.remote_addr not in (None, "127.0.0.1", "::1"):
            return jsonify(error="Yalnızca yerel erişim desteklenir."), 403
        if request.method == "POST":
            origin = request.headers.get("Origin")
            if origin and origin.rstrip("/") != request.host_url.rstrip("/"):
                return jsonify(error="İstek kaynağı reddedildi."), 403
            token = session.get("csrf_token")
            supplied = request.headers.get("X-CSRF-Token", "")
            if not token or not supplied.isascii() or not secrets.compare_digest(token, supplied):
                return jsonify(error="Oturum doğrulanamadı; sayfayı yenileyin."), 403

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(self), microphone=()"
        if request.path == "/" or request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(HTTPException)
    def http_error(error):
        message = (
            error.description
            if error.code == 400
            else {
                404: "Adres bulunamadı.",
                405: "İstek yöntemi desteklenmiyor.",
                413: "İstek boyutu sınırı aşıldı.",
                415: "JSON gövdesi gereklidir.",
            }.get(error.code, "İstek işlenemedi.")
        )
        return jsonify(error=message), error.code

    @app.errorhandler(Exception)
    def internal_error(error):
        app.logger.exception("İstek işlenemedi")
        return jsonify(
            error="İşlem tamamlanamadı. Kayıtlar korunmuştur; sunucu günlüğünü kontrol edin."
        ), 500

    @app.get("/")
    def index():
        session.setdefault("csrf_token", secrets.token_urlsafe(32))
        return render_template("index.html", csrf_token=session["csrf_token"])

    @app.get("/static/css/style.css")
    def stylesheet():
        return send_from_directory(BASE_DIR, "style.css")

    @app.get("/static/js/app.js")
    def script():
        return send_from_directory(BASE_DIR, "app.js")

    @app.get("/api/health")
    def health():
        return jsonify(
            mode=app.config["MODE"], demo=app.config["DEMO"], recognition=recognition_status()
        )

    @app.get("/api/attendance")
    def attendance():
        return jsonify(attendance_payload())

    @app.get("/api/students/<sid>/photo")
    def student_photo(sid):
        student = next((s for s in manager.get_all_students() if s["id"] == sid), {})
        path = reference_photo_path(faces_dir, student.get("filename"))
        if path is None:
            return jsonify(error="Öğrenci fotoğrafı bulunamadı."), 404
        return send_file(path, conditional=True)

    @app.get("/api/students")
    def students():
        roster = current_roster()
        return jsonify(students=roster, count=len(roster))

    @app.post("/api/attendance/toggle")
    def toggle():
        sid = _json_body().get("id")
        if not isinstance(sid, str) or not sid or len(sid) > 64:
            raise BadRequest("Geçerli öğrenci numarası gereklidir.")
        try:
            return jsonify(success=True, student=store.toggle(sid))
        except KeyError:
            return jsonify(error="Öğrenci bulunamadı."), 404

    @app.post("/api/attendance/save")
    def save():
        _json_body()
        filename = store.save()
        return jsonify(success=True, filename=filename, message="Yoklama kaydedildi.")

    @app.post("/api/attendance/reset")
    def reset():
        _json_body()
        with reload_lock:
            filename = store.reset(current_roster())
        return jsonify(
            success=True,
            filename=filename,
            message="Önceki yoklama arşivlendi; yeni yoklama başlatıldı.",
        )

    @app.post("/api/reload-faces")
    def reload_faces():
        _json_body()
        with reload_lock:
            if app.config["MODE"] == "recognition":
                manager.load_faces()
                status = recognition_status()
                if status.get("error"):
                    return jsonify(error=status["error"], recognition=status), 503
            try:
                roster = current_roster()
            except (ValueError, TypeError, KeyError):
                return jsonify(error="Öğrenci dosyası geçersiz; mevcut yoklama korunmuştur."), 400
            store.sync_roster(roster)
        return jsonify(
            success=True,
            count=len(roster),
            recognition=recognition_status(),
            message=f"{len(roster)} öğrenci yüklendi; mevcut yoklama korundu.",
        )

    @app.post("/api/recognize")
    def recognize():
        data = _json_body()
        frame = decode_image(data.get("image"))
        generation = store.snapshot()["generation"]
        if "generation" in data and data["generation"] != generation:
            return jsonify(error="Yoklama oturumu değişti; eski görüntü atlandı."), 409
        if app.config["MODE"] == "manual" or not recognition_status().get("available"):
            return jsonify(error="Yüz tanıma hazır değil. Durum bilgisini kontrol edin."), 503
        if not recognition_lock.acquire(blocking=False):
            return jsonify(error="Önceki görüntü işleniyor."), 429
        try:
            faces = recognize_frame(manager, frame)
            # Model çalışırken yeni yoklama açılmış olabilir; depo kimliği tekrar sınar.
            marked = store.mark_recognized(faces, generation)
            if marked is None:
                return jsonify(error="Yoklama oturumu değişti; eski görüntü atlandı."), 409
            snapshot = attendance_payload()
            return jsonify(
                faces=faces,
                newly_marked=marked,
                attendance=snapshot["students"],
                stats=snapshot["stats"],
                generation=snapshot["generation"],
            )
        except (FaceRecognitionUnavailable, FaceRecognitionError):
            app.logger.exception("Yüz tanıma tamamlanamadı")
            return jsonify(error="Yüz tanıma tamamlanamadı; manuel yoklama kullanılabilir."), 503
        finally:
            recognition_lock.release()

    @app.get("/api/attendance/pdf")
    def pdf():
        snapshot = store.snapshot()
        target = io.BytesIO()
        generate_pdf(snapshot["students"], output_path=target, session_date=snapshot["date"])
        target.seek(0)
        return send_file(
            target,
            as_attachment=True,
            download_name=f"yoklama_{datetime.now():%Y%m%d_%H%M%S_%f}.pdf",
            mimetype="application/pdf",
        )

    return app


def main():
    """Yerel ayarları oku ve yalnız bu bilgisayardan erişilen sunucuyu başlat."""
    from dotenv import load_dotenv
    from waitress import serve

    # Model loglarındaki Türkçe/emoji, eski Windows konsol kodlamasını bozmasın.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    load_dotenv(BASE_DIR / ".env")
    os.environ["DEEPFACE_HOME"] = str(
        _resolve_path(os.getenv("DEEPFACE_HOME") or str(BASE_DIR / ".models"))
    )
    parser = argparse.ArgumentParser(description="YoklamaX yerel yoklama sunucusu")
    parser.add_argument(
        "--demo", action="store_true", help="Kurmaca öğrenci listesiyle manuel demo"
    )
    parser.add_argument("--mode", choices=["manual", "recognition"])
    parser.add_argument("--port", type=int, default=int(os.getenv("YOKLAMAX_PORT", "5050")))
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port 1–65535 aralığında olmalıdır.")
    overrides = {}
    if args.demo:
        overrides.update(DEMO=True, DATA_DIR=str(BASE_DIR / "data" / "demo"))
    if args.mode:
        overrides["MODE"] = args.mode
    logging.basicConfig(level=logging.INFO)
    app = create_app(overrides)
    logging.info(
        "YoklamaX: http://127.0.0.1:%s | %s%s",
        args.port,
        app.config["MODE"],
        " | kurmaca demo" if app.config["DEMO"] else "",
    )
    serve(app, host="127.0.0.1", port=args.port, threads=4)


if __name__ == "__main__":
    main()
