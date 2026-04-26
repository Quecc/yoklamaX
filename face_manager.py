"""
Yüz Tanıma Yönetim Modülü
/faces/ klasöründeki referans fotoğrafları yükler, embedding hesaplar
ve canlı frame'lerdeki yüzlerle karşılaştırır.
DeepFace kütüphanesi kullanır (dlib bağımlılığı yok).
"""

import os
import cv2
import numpy as np
from deepface import DeepFace


class FaceManager:
    """Yüz verisi yükleme ve eşleştirme sınıfı."""

    SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}

    def __init__(self, faces_dir="faces/"):
        self.faces_dir = faces_dir
        self.known_embeddings = []   # List of embedding arrays
        self.known_metadata = []     # List of {id, name, filename}
        self.is_loaded = False
        self.model_name = "Facenet"  # Hafif ve doğru model
        self.detector_backend = "opencv"  # Hızlı yüz tespiti
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )

    def _parse_filename(self, filename):
        """
        Dosya adından öğrenci bilgisi çıkarır.
        Format: numara_isim.jpg → {id: "12345", name: "Ahmet"}
        """
        name_part = os.path.splitext(filename)[0]
        parts = name_part.split('_', 1)

        if len(parts) == 2 and parts[0].isdigit():
            student_id = parts[0]
            student_name = parts[1].replace('_', ' ').title()
        else:
            student_id = "N/A"
            student_name = name_part.replace('_', ' ').title()

        return {"id": student_id, "name": student_name, "filename": filename}

    def load_faces(self):
        """
        /faces/ klasöründeki tüm desteklenen formattaki dosyaları tarar,
        yüz embedding'lerini hesaplar ve saklar.
        """
        self.known_embeddings = []
        self.known_metadata = []

        if not os.path.exists(self.faces_dir):
            os.makedirs(self.faces_dir, exist_ok=True)
            print(f"[FaceManager] '{self.faces_dir}' klasörü oluşturuldu.")
            self.is_loaded = True
            return 0

        loaded_count = 0
        skipped = []

        for filename in sorted(os.listdir(self.faces_dir)):
            ext = os.path.splitext(filename)[1].lower()
            if ext not in self.SUPPORTED_EXTENSIONS:
                continue

            filepath = os.path.join(self.faces_dir, filename)

            try:
                # DeepFace ile embedding hesapla
                result = DeepFace.represent(
                    img_path=filepath,
                    model_name=self.model_name,
                    detector_backend=self.detector_backend,
                    enforce_detection=False
                )

                if result and len(result) > 0:
                    embedding = np.array(result[0]["embedding"])
                    metadata = self._parse_filename(filename)

                    self.known_embeddings.append(embedding)
                    self.known_metadata.append(metadata)
                    loaded_count += 1
                    print(f"  ✓ {filename} → {metadata['name']} ({metadata['id']})")
                else:
                    skipped.append(f"{filename} (yüz bulunamadı)")

            except Exception as e:
                skipped.append(f"{filename} (hata: {str(e)[:80]})")

        self.is_loaded = True

        if skipped:
            print(f"\n[FaceManager] Atlanan dosyalar:")
            for s in skipped:
                print(f"  ✗ {s}")

        print(f"\n[FaceManager] Toplam {loaded_count} yüz yüklendi.")
        return loaded_count

    def _cosine_distance(self, emb1, emb2):
        """İki embedding arasındaki cosine distance hesaplar."""
        dot = np.dot(emb1, emb2)
        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)
        if norm1 == 0 or norm2 == 0:
            return 1.0
        similarity = dot / (norm1 * norm2)
        return 1.0 - similarity

    def recognize(self, frame, tolerance=0.35):
        """
        Verilen frame (numpy array, BGR) içindeki yüzleri bulur
        ve bilinen yüzlerle karşılaştırır.

        Returns:
            list of dict: Her tespit edilen yüz için bilgi
        """
        results = []

        # OpenCV Haar cascade ile yüz tespiti (hızlı)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces_detected = self.face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60)
        )

        if len(faces_detected) == 0:
            return results

        for (x, y, w, h) in faces_detected:
            # Yüz bölgesini kırp (biraz margin ekle)
            margin = int(w * 0.15)
            y1 = max(0, y - margin)
            y2 = min(frame.shape[0], y + h + margin)
            x1 = max(0, x - margin)
            x2 = min(frame.shape[1], x + w + margin)
            face_crop = frame[y1:y2, x1:x2]

            if face_crop.size == 0:
                continue

            face_result = {
                "id": None,
                "name": "Bilinmeyen",
                "box": {"top": int(y), "right": int(x + w), "bottom": int(y + h), "left": int(x)},
                "distance": 1.0,
                "matched": False
            }

            # Bilinen yüzler varsa eşleştir
            if self.is_loaded and len(self.known_embeddings) > 0:
                try:
                    # Yüz embedding'ini hesapla
                    emb_result = DeepFace.represent(
                        img_path=face_crop,
                        model_name=self.model_name,
                        detector_backend="skip",  # zaten kırptık
                        enforce_detection=False
                    )

                    if emb_result and len(emb_result) > 0:
                        face_embedding = np.array(emb_result[0]["embedding"])

                        # Tüm bilinen yüzlerle karşılaştır
                        distances = [
                            self._cosine_distance(face_embedding, known_emb)
                            for known_emb in self.known_embeddings
                        ]

                        best_idx = np.argmin(distances)
                        best_distance = distances[best_idx]

                        if best_distance <= tolerance:
                            metadata = self.known_metadata[best_idx]
                            face_result["id"] = metadata["id"]
                            face_result["name"] = metadata["name"]
                            face_result["distance"] = round(float(best_distance), 3)
                            face_result["matched"] = True

                except Exception as e:
                    print(f"[FaceManager] Eşleştirme hatası: {str(e)[:100]}")

            results.append(face_result)

        return results

    def get_all_students(self):
        """Kayıtlı tüm öğrencilerin listesini döner."""
        return [
            {"id": m["id"], "name": m["name"], "filename": m["filename"]}
            for m in self.known_metadata
        ]

    def get_student_count(self):
        """Kayıtlı öğrenci sayısını döner."""
        return len(self.known_metadata)
