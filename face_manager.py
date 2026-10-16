"""Fotoğraf klasörünü öğrenci listesine çevirir ve kameradaki yüzleri eşleştirir.

OpenCV yüzü bulup kırpar; Facenet bu parçadan bir sayı dizisi (embedding) çıkarır.
Kamera ve referans fotoğrafı aynı işlemlerden geçer. DeepFace yalnız gerektiğinde
yüklenir; böylece manuel yoklama TensorFlow kurulumu olmadan da çalışabilir.
"""

import importlib
import io
import os
import re
import threading
import warnings

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError


class FaceRecognitionError(RuntimeError):
    """Yüz tespiti veya model hesabı tamamlanamadı."""


class FaceRecognitionUnavailable(FaceRecognitionError):
    """Tanıma bağımlılıkları ya da geçerli referans yüzleri hazır değil."""


class FaceManager:
    """Referansların ve modelin tek sahibi; yoklama dosyasına yazmaz."""

    SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    MAX_REFERENCE_BYTES = 4 * 1024 * 1024
    MAX_REFERENCE_PIXELS = 8_000_000
    MAX_REFERENCE_DIMENSION = 4096
    # İki kişiye çok yakın sonuç çıkarsa birini rastgele var sayma.
    MIN_MATCH_MARGIN = 0.02

    def __init__(self, faces_dir="faces/"):
        self.faces_dir = os.fspath(faces_dir)
        self.known_embeddings = []
        self.known_metadata = []
        self.is_loaded = False
        self.model_name = "Facenet"
        self.detector_backend = "opencv"
        self.face_cascade = cv2.CascadeClassifier(
            os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        )
        self.eye_cascade = cv2.CascadeClassifier(
            os.path.join(cv2.data.haarcascades, "haarcascade_eye_tree_eyeglasses.xml")
        )
        self._state_lock = threading.RLock()
        self._load_lock = threading.Lock()
        self._model_lock = threading.Lock()
        self._detector_lock = threading.Lock()
        self._backend = None
        self._available = False
        self._error = None
        self._skipped = []
        self._loading = False

    def _parse_filename(self, filename):
        """numara_ad_soyad biçiminden öğrenci bilgilerini oku."""
        stem = os.path.splitext(os.path.basename(filename))[0]
        match = re.fullmatch(r"([0-9]{1,32})_(.+)", stem)
        if not match:
            raise ValueError("Dosya adı numara_isim biçiminde olmalı")
        name = " ".join(match.group(2).replace("_", " ").split())
        if not name or len(name) > 100 or not any(c.isalpha() for c in name):
            raise ValueError("Öğrenci adı geçersiz")
        if any(ord(c) < 32 or ord(c) == 127 for c in match.group(2)):
            raise ValueError("Öğrenci adı kontrol karakteri içeremez")
        return {"id": match.group(1), "name": name.title(), "filename": filename}

    def _read_image(self, filepath):
        # Windows'taki Türkçe dosya adlarını Python ile oku. Boyutu, OpenCV
        # görüntüyü belleğe açmadan önce denetle.
        with open(filepath, "rb") as source:
            raw = source.read(self.MAX_REFERENCE_BYTES + 1)
        if not raw:
            raise ValueError("Görüntü dosyası boş")
        if len(raw) > self.MAX_REFERENCE_BYTES:
            raise ValueError("Referans fotoğraf en fazla 4 MB olmalı")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw), formats=["JPEG", "PNG", "WEBP", "BMP"]) as image:
                    width, height = image.size
                    if (
                        min(width, height) < 2
                        or max(width, height) > self.MAX_REFERENCE_DIMENSION
                        or width * height > self.MAX_REFERENCE_PIXELS
                    ):
                        raise ValueError(
                            "Referans fotoğraf 2–4096 piksel ve en fazla 8 megapiksel olmalı"
                        )
        except (
            UnidentifiedImageError,
            OSError,
            Image.DecompressionBombWarning,
            Image.DecompressionBombError,
        ) as exc:
            raise ValueError("Görüntü başlığı okunamadı veya boyutu çok büyük") from exc
        encoded = np.frombuffer(raw, dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Görüntü okunamadı")
        return image

    def _detect_faces(self, frame):
        if (
            not isinstance(frame, np.ndarray)
            or frame.ndim != 3
            or frame.shape[2] != 3
            or frame.size == 0
            or frame.dtype != np.uint8
        ):
            raise ValueError("Görüntü, boş olmayan bir BGR uint8 dizisi olmalı")
        if self.face_cascade.empty():
            raise FaceRecognitionError("OpenCV yüz algılama modeli yüklenemedi")
        if self.eye_cascade.empty():
            raise FaceRecognitionError("OpenCV göz doğrulama modeli yüklenemedi")
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        with self._detector_lock:
            detected = self.face_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60)
            )
            boxes = [tuple(int(value) for value in box) for box in detected]
            return [box for box in boxes if self._has_eye_pair(gray, box)]

    def _has_eye_pair(self, gray, box):
        """İki gözün konumuyla kravat/arka plan gibi yanlış yüz adaylarını ele.

        Çağıran kod detector kilidini tutar. Bu bir canlılık kontrolü değildir.
        """
        x, y, width, height = box
        upper_face = gray[y : y + round(height * 0.65), x : x + width]
        if not upper_face.size:
            return False
        eyes = self.eye_cascade.detectMultiScale(
            upper_face,
            scaleFactor=1.1,
            minNeighbors=4,
            minSize=(max(8, width // 10), max(8, height // 10)),
        )
        centers = [(ex + ew / 2, ey + eh / 2) for ex, ey, ew, eh in eyes]
        for left in centers:
            for right in centers:
                if (
                    left[0] < width / 2 < right[0]
                    and width * 0.2 <= right[0] - left[0] <= width * 0.65
                    and abs(left[1] - right[1]) <= height * 0.15
                ):
                    return True
        return False

    @staticmethod
    def _crop_face(frame, box):
        x, y, width, height = box
        margin = int(width * 0.15)
        crop = frame[
            max(0, y - margin) : min(frame.shape[0], y + height + margin),
            max(0, x - margin) : min(frame.shape[1], x + width + margin),
        ]
        if crop.size == 0:
            raise FaceRecognitionError("Algılanan yüz bölgesi boş")
        return crop

    def _get_backend(self):
        # Çağıran _represent, model kilidini tutar; aynı anda iki model yüklenmez.
        if self._backend is None:
            try:
                self._backend = importlib.import_module("deepface.DeepFace")
            except Exception as exc:
                raise FaceRecognitionUnavailable(
                    "Yüz tanıma bağımlılıkları yüklenemedi. "
                    "requirements-recognition.txt kurulumunu kontrol edin; manuel yoklama kullanılabilir."
                ) from exc
        return self._backend

    def _represent(self, crop):
        try:
            with self._model_lock:
                result = self._get_backend().represent(
                    img_path=crop,
                    model_name=self.model_name,
                    detector_backend="skip",
                    enforce_detection=False,
                )
            if not isinstance(result, list) or len(result) != 1:
                raise ValueError("Model tek bir embedding döndürmedi")
            embedding = np.asarray(result[0]["embedding"], dtype=np.float64)
            norm = np.linalg.norm(embedding)
            if (
                embedding.ndim != 1
                or embedding.size < 2
                or not np.all(np.isfinite(embedding))
                or not np.isfinite(norm)
                or norm == 0
            ):
                raise ValueError("Model geçerli bir embedding döndürmedi")
            embedding.setflags(write=False)
            return embedding
        except FaceRecognitionError:
            raise
        except Exception as exc:
            raise FaceRecognitionError(
                "Facenet yüz tanıma işlemi başarısız oldu. "
                "Model dosyalarını ve yüz tanıma kurulumunu kontrol edin."
            ) from exc

    def _snapshot(self):
        with self._state_lock:
            return tuple(self.known_embeddings), tuple(dict(m) for m in self.known_metadata)

    def _commit(self, embeddings, metadata, skipped, available, error=None):
        with self._state_lock:
            self.known_embeddings = list(embeddings)
            self.known_metadata = [dict(m) for m in metadata]
            self.is_loaded = True
            self._skipped = list(skipped)
            self._available = available
            self._error = error

    def _read_references(self, files, skipped):
        """Dosya adlarını doğrula; kişi başına tek yüz içeren fotoğrafları al."""
        parsed = []
        counts = {}
        for filename in files:
            try:
                student = self._parse_filename(filename)
                parsed.append(student)
                student_id = student["id"]
                counts[student_id] = counts.get(student_id, 0) + 1
            except ValueError as exc:
                skipped.append({"filename": filename, "reason": str(exc)})

        candidates = []
        for student in parsed:
            filename = student["filename"]
            if counts[student["id"]] != 1:
                skipped.append(
                    {
                        "filename": filename,
                        "reason": "Öğrenci numarası birden fazla dosyada kullanılmış",
                    }
                )
                continue
            try:
                image = self._read_image(os.path.join(self.faces_dir, filename))
                boxes = self._detect_faces(image)
                if len(boxes) != 1:
                    reason = (
                        "Fotoğrafta yüz bulunamadı"
                        if not boxes
                        else "Fotoğrafta birden fazla yüz var"
                    )
                    skipped.append({"filename": filename, "reason": reason})
                    continue
                candidates.append((student, self._crop_face(image, boxes[0])))
            except (OSError, ValueError, cv2.error) as exc:
                # İşletim sistemi hataları yerel dosya yollarını içerebilir.
                reason = str(exc) if isinstance(exc, ValueError) else "Görüntü okunamadı"
                skipped.append({"filename": filename, "reason": reason})
        return candidates

    def _make_embeddings(self, candidates):
        embeddings = []
        for _, crop in candidates:
            embedding = self._represent(crop)
            if embeddings and embedding.shape != embeddings[0].shape:
                raise FaceRecognitionError("Referans embedding boyutları uyuşmuyor")
            embeddings.append(embedding)
        return embeddings

    def _record_load_error(self, message, skipped, disable_recognition=False):
        """Önceki öğrenci listesini silmeden yükleme hatasını görünür yap."""
        with self._state_lock:
            self._error = message
            self._skipped = list(skipped)
            if disable_recognition:
                self._available = False

    def load_faces(self, load_embeddings=True):
        """Referansları hazırla, sonra tek seferde değiştir; hazır yüz sayısını döndür.

        Hatalı yenileme önceki listeyi korur. Boş klasör listeyi boşaltır.
        load_embeddings=False, model yüklemeden fotoğraflardan manuel liste çıkarır.
        """
        with self._load_lock:
            with self._state_lock:
                self._loading = True
            previous_embeddings, previous_metadata = self._snapshot()
            skipped = []
            try:
                if not os.path.exists(self.faces_dir):
                    if previous_metadata:
                        raise OSError("Referans fotoğraf klasörü bulunamadı")
                    os.makedirs(self.faces_dir, exist_ok=True)
                files = sorted(
                    name
                    for name in os.listdir(self.faces_dir)
                    if os.path.splitext(name)[1].lower() in self.SUPPORTED_EXTENSIONS
                )
                candidates = self._read_references(files, skipped)
                previous_files = {m["filename"] for m in previous_metadata}
                previous_file_failed = any(entry["filename"] in previous_files for entry in skipped)
                all_files_failed = previous_metadata and files and not candidates
                if previous_file_failed or all_files_failed:
                    self._record_load_error(
                        "Referanslar yüklenemedi; önceki geçerli veriler korundu.", skipped
                    )
                    return len(previous_embeddings)

                metadata = [entry[0] for entry in candidates]
                embeddings = []
                if load_embeddings and candidates:
                    try:
                        embeddings = self._make_embeddings(candidates)
                    except FaceRecognitionError as exc:
                        if previous_metadata:
                            self._record_load_error(str(exc), skipped, disable_recognition=True)
                            return len(previous_embeddings)
                        # İlk açılışta model çalışmasa da manuel liste kullanılabilsin.
                        self._commit([], metadata, skipped, False, str(exc))
                        return 0
                self._commit(embeddings, metadata, skipped, bool(embeddings))
                return len(embeddings)
            except (OSError, FaceRecognitionError, cv2.error) as exc:
                message = "Referans fotoğraflar okunamadı; önceki veriler korundu."
                if isinstance(exc, FaceRecognitionError):
                    message = str(exc)
                self._record_load_error(message, skipped)
                return len(previous_embeddings)
            finally:
                with self._state_lock:
                    self._loading = False

    @staticmethod
    def _cosine_distance(emb1, emb2):
        if emb1.shape != emb2.shape:
            raise FaceRecognitionError("Yüz embedding boyutları uyuşmuyor")
        norm1, norm2 = np.linalg.norm(emb1), np.linalg.norm(emb2)
        if not np.isfinite(norm1) or not np.isfinite(norm2) or norm1 == 0 or norm2 == 0:
            raise FaceRecognitionError("Yüz embedding normu geçersiz")
        similarity = float(np.dot(emb1 / norm1, emb2 / norm2))
        return 1.0 - float(np.clip(similarity, -1.0, 1.0))

    def _match_embedding(self, embedding, embeddings, metadata, tolerance):
        """En yakın öğrenciyi seç; eşik dışındaki ve belirsiz sonuçları reddet."""
        distances = [self._cosine_distance(embedding, known) for known in embeddings]
        best_index = int(np.argmin(distances))
        distance = float(distances[best_index])
        student = metadata[best_index]
        competitors = [
            value for index, value in enumerate(distances) if metadata[index]["id"] != student["id"]
        ]
        ambiguous = bool(competitors) and min(competitors) - distance < self.MIN_MATCH_MARGIN
        matched = distance <= tolerance and not ambiguous
        return {
            "id": student["id"] if matched else None,
            "name": student["name"] if matched else "Bilinmeyen",
            "distance": round(distance, 3),
            "matched": matched,
        }

    def recognize(self, frame, tolerance=0.35):
        """Yüzleri bul → kırp → sayı dizisine çevir → referanslarla karşılaştır."""
        if (
            not isinstance(tolerance, (int, float))
            or not np.isfinite(tolerance)
            or not 0 <= tolerance <= 1
        ):
            raise ValueError("Eşleştirme eşiği 0 ile 1 arasında olmalı")
        with self._state_lock:
            embeddings, metadata = self._snapshot()
            available = self._available
            error = self._error
        if not available or not embeddings:
            raise FaceRecognitionUnavailable(
                error or "Yüz tanıma için geçerli referans embedding bulunamadı"
            )
        try:
            results = []
            for x, y, width, height in self._detect_faces(frame):
                embedding = self._represent(self._crop_face(frame, (x, y, width, height)))
                match = self._match_embedding(embedding, embeddings, metadata, tolerance)
                match["box"] = {"top": y, "right": x + width, "bottom": y + height, "left": x}
                results.append(match)
            return results
        except (FaceRecognitionError, cv2.error) as exc:
            error = (
                exc
                if isinstance(exc, FaceRecognitionError)
                else FaceRecognitionError("OpenCV yüz algılama işlemi başarısız oldu")
            )
            with self._state_lock:
                self._available = False
                self._error = str(error)
            if error is exc:
                raise
            raise error from exc

    def get_all_students(self):
        with self._state_lock:
            return [dict(metadata) for metadata in self.known_metadata]

    def get_student_count(self):
        with self._state_lock:
            return len(self.known_metadata)

    def status(self):
        with self._state_lock:
            return {
                "loaded_count": len(self.known_embeddings),
                "skipped": [dict(entry) for entry in self._skipped],
                "available": self._available,
                "error": self._error,
                "loading": self._loading,
            }
