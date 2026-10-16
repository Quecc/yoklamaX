"""Face pipeline contracts tested with drawings and synthetic vectors only."""

import tempfile
import threading
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch
from unittest.mock import Mock

import cv2
import numpy as np

from face_manager import FaceManager, FaceRecognitionError, FaceRecognitionUnavailable


class StubModel:
    def __init__(self, vector=None):
        self.vector = [1.0, 0.0, 0.0] if vector is None else vector
        self.calls = []

    def represent(self, **kwargs):
        self.calls.append({**kwargs, "img_path": kwargs["img_path"].copy()})
        return [{"embedding": self.vector}]


class FaceManagerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.faces = Path(self.directory.name) / "fotoğraflar_ışık"
        self.faces.mkdir()
        self.manager = FaceManager(self.faces)
        self.model = StubModel()
        self.manager._backend = self.model
        self.image = np.zeros((100, 120, 3), dtype=np.uint8)
        self.image[:, :, 0] = np.arange(120, dtype=np.uint8)
        self.image[:, :, 1] = np.arange(100, dtype=np.uint8)[:, None]
        self.boxes = [(20, 10, 60, 60)]

    def write_image(self, filename="001_ışık_yılmaz.png"):
        target = self.faces / filename
        success, encoded = cv2.imencode(".png", self.image)
        self.assertTrue(success)
        encoded.tofile(target)
        return target

    def load_one(self):
        self.write_image()
        with patch.object(self.manager, "_detect_faces", return_value=self.boxes):
            self.assertEqual(self.manager.load_faces(), 1)

    def test_filename_validation_prevents_na_and_unicode_digit_collisions(self):
        for filename in ["someone.png", "123_.jpg", "12_123.png", "١٢_ahmet.png", "1_ah\nmet.png"]:
            with self.subTest(filename=filename), self.assertRaises(ValueError):
                self.manager._parse_filename(filename)
        self.assertEqual(self.manager._parse_filename("001_ışık_yılmaz.png")["id"], "001")

    def test_initialization_and_empty_directory_do_not_import_deepface(self):
        with patch("face_manager.importlib.import_module", side_effect=AssertionError("Must not import")):
            manager = FaceManager(self.faces)
            self.assertEqual(manager.load_faces(), 0)
            self.assertEqual(manager.get_all_students(), [])
            self.assertFalse(manager.status()["available"])

    def test_eye_filter_rejects_garment_without_losing_a_real_face(self):
        frame = np.zeros((200, 100, 3), dtype=np.uint8)
        self.manager.face_cascade = Mock()
        self.manager.face_cascade.empty.return_value = False
        self.manager.face_cascade.detectMultiScale.return_value = [(10, 10, 80, 80),
                                                                 (10, 100, 80, 80)]
        self.manager.eye_cascade = Mock()
        self.manager.eye_cascade.empty.return_value = False
        self.manager.eye_cascade.detectMultiScale.side_effect = [
            [(13, 18, 14, 12), (51, 19, 14, 12)], [],
        ]
        self.assertEqual(self.manager._detect_faces(frame), [(10, 10, 80, 80)])

    def test_eye_filter_does_not_accept_two_detections_on_same_side(self):
        self.manager.eye_cascade = Mock()
        self.manager.eye_cascade.detectMultiScale.return_value = [(4, 10, 12, 12),
                                                                 (15, 12, 12, 12)]
        self.assertFalse(self.manager._has_eye_pair(np.zeros((100, 100), np.uint8),
                                                  (10, 10, 80, 80)))

    def test_photo_manual_roster_loading_does_not_import_deepface(self):
        self.write_image()
        self.manager._backend = None
        with patch.object(self.manager, "_detect_faces", return_value=self.boxes), patch(
            "face_manager.importlib.import_module", side_effect=AssertionError("Must not import")
        ):
            self.assertEqual(self.manager.load_faces(load_embeddings=False), 0)
        self.assertEqual(self.manager.get_student_count(), 1)
        self.assertFalse(self.manager.status()["available"])
        self.assertIsNone(self.manager.status()["error"])

    def test_lazy_import_targets_deepface_submodule_and_caches_it(self):
        # deepface/__init__.py exposes a version, not the DeepFace attribute;
        # importing the public submodule also works in a fresh process.
        self.manager._backend = None
        with patch("face_manager.importlib.import_module", return_value=self.model) as importer:
            first = self.manager._represent(self.image)
            second = self.manager._represent(self.image)
        importer.assert_called_once_with("deepface.DeepFace")
        np.testing.assert_array_equal(first, second)
        self.assertEqual(len(self.model.calls), 2)

    def test_unicode_image_and_identical_reference_probe_preprocessing(self):
        self.load_one()
        with patch.object(self.manager, "_detect_faces", return_value=self.boxes):
            result = self.manager.recognize(self.image)
        self.assertTrue(result[0]["matched"])
        self.assertEqual(result[0]["id"], "001")
        self.assertEqual(result[0]["box"], {"top": 10, "left": 20, "right": 80, "bottom": 70})
        self.assertEqual(len(self.model.calls), 2)
        for call in self.model.calls:
            self.assertEqual(call["model_name"], "Facenet")
            self.assertEqual(call["detector_backend"], "skip")
        np.testing.assert_array_equal(self.model.calls[0]["img_path"], self.model.calls[1]["img_path"])

    def test_no_face_and_multiple_faces_are_never_used_as_references(self):
        self.write_image()
        for boxes in [[], [(0, 0, 60, 60), (60, 0, 60, 60)]]:
            with self.subTest(boxes=boxes), patch.object(self.manager, "_detect_faces", return_value=boxes):
                self.assertEqual(self.manager.load_faces(), 0)
                self.assertEqual(self.manager.get_all_students(), [])
                self.assertEqual(len(self.manager.status()["skipped"]), 1)
        self.assertEqual(self.model.calls, [])

    def test_duplicate_ids_reject_both_files(self):
        self.write_image("001_ışık.png")
        self.write_image("001_elif.png")
        with patch.object(self.manager, "_detect_faces", return_value=self.boxes):
            self.assertEqual(self.manager.load_faces(), 0)
        self.assertEqual(self.manager.get_student_count(), 0)
        self.assertEqual(len(self.manager.status()["skipped"]), 2)
        self.assertEqual(self.model.calls, [])

    def test_oversized_compressed_reference_is_rejected_before_decode(self):
        target = self.faces / "001_ışık.png"
        with target.open("wb") as source:
            source.seek(self.manager.MAX_REFERENCE_BYTES)
            source.write(b"\0")
        with patch("face_manager.cv2.imdecode") as decoder, self.assertRaises(ValueError):
            self.manager._read_image(target)
        decoder.assert_not_called()

    def test_large_dimension_or_pixel_header_is_rejected_before_decode(self):
        target = self.write_image()
        original = target.read_bytes()
        for width, height in [(4097, 10), (3000, 3000)]:
            with self.subTest(width=width, height=height):
                # Alter only the PNG header; no large image allocation is used.
                oversized = bytearray(original)
                oversized[16:20] = width.to_bytes(4, "big")
                oversized[20:24] = height.to_bytes(4, "big")
                oversized[29:33] = zlib.crc32(oversized[12:29]).to_bytes(4, "big")
                target.write_bytes(oversized)
                with patch("face_manager.cv2.imdecode") as decoder, self.assertRaises(ValueError):
                    self.manager._read_image(target)
                decoder.assert_not_called()

    def test_model_unavailable_keeps_manual_roster_without_claiming_ready(self):
        self.write_image()
        self.manager._backend = None
        with patch.object(self.manager, "_detect_faces", return_value=self.boxes), patch(
            "face_manager.importlib.import_module", side_effect=ImportError("SECRET_VALUE")
        ):
            self.assertEqual(self.manager.load_faces(), 0)
        self.assertEqual(self.manager.get_student_count(), 1)
        status = self.manager.status()
        self.assertFalse(status["available"])
        self.assertIsNotNone(status["error"])
        self.assertNotIn("SECRET_VALUE", status["error"])
        with self.assertRaises(FaceRecognitionUnavailable):
            self.manager.recognize(self.image)

    def test_partial_inference_failure_preserves_previous_snapshot(self):
        self.load_one()
        original_students = self.manager.get_all_students()
        self.write_image("002_elif.png")
        with patch.object(self.manager, "_detect_faces", return_value=self.boxes), patch.object(
            self.manager, "_represent", side_effect=[np.array([0, 1, 0]), FaceRecognitionError("Test model failure")]
        ):
            self.assertEqual(self.manager.load_faces(), 1)
        self.assertEqual(self.manager.get_all_students(), original_students)
        np.testing.assert_array_equal(self.manager.known_embeddings[0], [1, 0, 0])
        self.assertIsNotNone(self.manager.status()["error"])
        self.assertFalse(self.manager.status()["loading"])

    def test_invalid_previous_reference_preserves_existing_data(self):
        self.load_one()
        with patch.object(self.manager, "_detect_faces", return_value=[]):
            self.assertEqual(self.manager.load_faces(), 1)
        self.assertEqual(self.manager.get_student_count(), 1)
        self.assertIsNotNone(self.manager.status()["error"])

    def test_all_new_invalid_files_also_preserve_previous_roster(self):
        self.load_one()
        (self.faces / "001_ışık_yılmaz.png").unlink()
        self.write_image("bad_filename.png")
        self.assertEqual(self.manager.load_faces(), 1)
        self.assertEqual(self.manager.get_all_students()[0]["id"], "001")
        self.assertIsNotNone(self.manager.status()["error"])

    def test_directory_io_failure_preserves_previous_data(self):
        self.load_one()
        with patch("face_manager.os.listdir", side_effect=PermissionError("SECRET_PATH")):
            self.assertEqual(self.manager.load_faces(), 1)
        self.assertEqual(self.manager.get_student_count(), 1)
        self.assertNotIn("SECRET_PATH", self.manager.status()["error"])

    def test_empty_directory_can_intentionally_clear_references(self):
        self.load_one()
        (self.faces / "001_ışık_yılmaz.png").unlink()
        self.assertEqual(self.manager.load_faces(), 0)
        self.assertEqual(self.manager.get_student_count(), 0)
        self.assertIsNone(self.manager.status()["error"])

    def test_inference_failure_is_propagated_not_unknown_match(self):
        self.load_one()
        with patch.object(self.manager, "_detect_faces", return_value=self.boxes), patch.object(
            self.model, "represent", side_effect=RuntimeError("SECRET_TOKEN")
        ), self.assertRaises(FaceRecognitionError) as caught:
            self.manager.recognize(self.image)
        self.assertNotIn("SECRET_TOKEN", str(caught.exception))
        self.assertFalse(self.manager.status()["available"])
        self.assertIsNotNone(self.manager.status()["error"])

    def test_unknown_face_reports_real_distance(self):
        self.load_one()
        self.model.vector = [0.0, 1.0, 0.0]
        with patch.object(self.manager, "_detect_faces", return_value=self.boxes):
            result = self.manager.recognize(self.image)
        self.assertFalse(result[0]["matched"])
        self.assertIsNone(result[0]["id"])
        self.assertEqual(result[0]["distance"], 1.0)

    def test_identical_vectors_for_different_students_are_ambiguous(self):
        self.write_image()
        self.write_image("002_elif.png")
        with patch.object(self.manager, "_detect_faces", return_value=self.boxes):
            self.assertEqual(self.manager.load_faces(), 2)
            result = self.manager.recognize(self.image)
        self.assertFalse(result[0]["matched"])
        self.assertIsNone(result[0]["id"])
        self.assertEqual(result[0]["distance"], 0.0)

    def test_close_competitor_is_ambiguous_but_distinct_competitor_matches(self):
        self.write_image()
        self.write_image("002_elif.png")
        for competitor, expected_match in [([1.0, 0.1, 0.0], False), ([0.0, 1.0, 0.0], True)]:
            with self.subTest(competitor=competitor), patch.object(
                self.manager, "_detect_faces", return_value=self.boxes
            ):
                with patch.object(self.manager, "_represent", side_effect=[
                    np.array([1.0, 0.0, 0.0]), np.array(competitor)
                ]):
                    self.assertEqual(self.manager.load_faces(), 2)
                result = self.manager.recognize(self.image)
            self.assertEqual(result[0]["matched"], expected_match)
            self.assertEqual(result[0]["id"], "001" if expected_match else None)

    def test_invalid_model_vectors_never_mark_attendance(self):
        for vector in [[0, 0, 0], [float("nan"), 1], [[1, 0]], [1]]:
            with self.subTest(vector=vector):
                self.model.vector = vector
                with self.assertRaises(FaceRecognitionError):
                    self.manager._represent(self.image)

    def test_probe_dimension_mismatch_is_propagated(self):
        self.load_one()
        self.model.vector = [1.0, 0.0]
        with patch.object(self.manager, "_detect_faces", return_value=self.boxes), self.assertRaises(FaceRecognitionError):
            self.manager.recognize(self.image)
        self.assertFalse(self.manager.status()["available"])

    def test_inflight_recognition_uses_one_consistent_roster_snapshot(self):
        self.load_one()
        inference_started = threading.Event()
        continue_inference = threading.Event()
        results = []
        errors = []

        def blocked_inference(crop):
            inference_started.set()
            if not continue_inference.wait(5):
                raise AssertionError("Test inference timeout")
            return np.array([1, 0, 0])

        def recognize():
            try:
                results.extend(self.manager.recognize(self.image))
            except Exception as exc:
                errors.append(exc)

        with patch.object(self.manager, "_detect_faces", return_value=self.boxes), patch.object(
            self.manager, "_represent", side_effect=blocked_inference
        ):
            thread = threading.Thread(target=recognize)
            thread.start()
            try:
                self.assertTrue(inference_started.wait(5))
                self.manager._commit([np.array([1, 0, 0])], [{"id": "002", "name": "Elif", "filename": "002_elif.png"}], [], True)
            finally:
                continue_inference.set()
                thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(results[0]["id"], "001")
        self.assertEqual(self.manager.get_all_students()[0]["id"], "002")

    def test_callers_cannot_mutate_roster_or_status(self):
        self.load_one()
        self.manager.get_all_students()[0]["id"] = "corrupted"
        self.assertEqual(self.manager.get_all_students()[0]["id"], "001")
        self.manager.status()["skipped"].append({"reason": "fake"})
        self.assertEqual(self.manager.status()["skipped"], [])


if __name__ == "__main__":
    unittest.main()
