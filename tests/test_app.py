"""API regression tests use temporary fictional data; no camera/model download."""

import base64
import importlib
import io
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
import zlib


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def synthetic_image(width=16, height=16):
    """Build a small valid PNG from synthetic pixels with standard libraries."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    pixels = b"".join(b"\x00" + b"\x00\x00\x00" * width for _ in range(height))
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(pixels))
           + chunk(b"IEND", b""))
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


class FakeFaceManager:
    """Deterministic recognition double with an optional inference callback."""

    def __init__(self, students):
        self.students = [dict(student) for student in students]
        self.is_loaded = False
        self.load_errors = []
        self.warnings = []
        self.recognition_calls = 0
        self.on_recognize = None

    def load_faces(self):
        self.is_loaded = True
        return len(self.students)

    def get_all_students(self):
        return [dict(student) for student in self.students]

    def get_student_count(self):
        return len(self.students)

    def recognize(self, frame, tolerance=0.35):
        self.recognition_calls += 1
        if self.on_recognize:
            self.on_recognize()
        student = self.students[0]
        return [{"id": student["id"], "name": student["name"], "matched": True,
                 "distance": 0.1, "box": {"top": 1, "right": 5, "bottom": 5, "left": 1}}]


class ImportTests(unittest.TestCase):
    def test_import_is_side_effect_free_and_does_not_load_ai_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(PROJECT_ROOT)
            completed = subprocess.run(
                [sys.executable, "-c", "import app, sys; "
                 "assert callable(app.create_app); "
                 "assert 'deepface' not in sys.modules; "
                 "assert 'tensorflow' not in sys.modules"],
                cwd=directory, env=environment, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(list(Path(directory).iterdir()), [])


class FrameScalingTests(unittest.TestCase):
    def test_recognition_boxes_return_to_original_image_coordinates(self):
        import app

        for width, height in [(1280, 720), (720, 1280), (320, 240), (4096, 2)]:
            with self.subTest(width=width, height=height):
                frame = app.np.zeros((height, width, 3), dtype=app.np.uint8)
                manager = mock.Mock()

                def whole_frame(small, tolerance):
                    self.assertLessEqual(max(small.shape[:2]), 640)
                    self.assertEqual(tolerance, 0.35)
                    return [{"box": {"top": 0, "left": 0,
                                     "bottom": small.shape[0], "right": small.shape[1]}}]

                manager.recognize.side_effect = whole_frame
                result = app.recognize_frame(manager, frame)
                self.assertEqual(result[0]["box"], {
                    "top": 0, "left": 0, "bottom": height, "right": width,
                })
                self.assertFalse(frame.any(), "İşlem kaynak görüntüyü değiştirmemeli")


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.data_dir = self.directory / "data"
        self.faces_dir = self.directory / "faces"
        self.data_dir.mkdir()
        self.faces_dir.mkdir()
        self.students = [
            {"id": "001", "name": "Örnek Öğrenci Çığdem"},
            {"id": "002", "name": "Deneme Şahin"},
        ]
        self.write_roster(self.students)
        self.config = {
            "TESTING": True,
            "SECRET_KEY": "fictional-unit-test-session-key",
            "MODE": "manual",
            "DEMO": False,
            "DATA_DIR": str(self.data_dir),
            "FACES_DIR": str(self.faces_dir),
        }
        self.module = importlib.import_module("app")
        self.app = self.module.create_app(self.config)
        self.client = self.app.test_client()
        self.headers = self.session_headers(self.client)

    def write_roster(self, students):
        (self.data_dir / "students.json").write_text(
            json.dumps(students, ensure_ascii=False), encoding="utf-8",
        )

    def session_headers(self, client):
        page = client.get("/")
        self.assertEqual(page.status_code, 200)
        with client.session_transaction() as session:
            self.assertIn("csrf_token", session)
            token = session["csrf_token"]
        self.assertIn(token.encode(), page.data)
        return {"X-CSRF-Token": token, "Origin": "http://localhost"}

    def post(self, path, payload=None, **kwargs):
        return self.client.post(path, json=payload, headers=self.headers, **kwargs)

    def attendance(self, client=None):
        response = (client or self.client).get("/api/attendance")
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def student(self, identifier="001", client=None):
        return next(student for student in self.attendance(client)["students"]
                    if student["id"] == identifier)

    def test_index_and_existing_static_assets_are_served(self):
        page = self.client.get("/")
        text = page.get_data(as_text=True)
        asset_paths = re.findall(r'(?:src|href)=[\'\"]([^\'\"]+\.(?:css|js)(?:\?[^\'\"]*)?)[\'\"]', text)
        local_assets = [path for path in asset_paths if path.startswith("/")]
        self.assertGreaterEqual(len(local_assets), 2)
        for path in local_assets:
            with self.subTest(path=path):
                response = self.client.get(path)
                try:
                    self.assertEqual(response.status_code, 200)
                    self.assertGreater(len(response.data), 100)
                finally:
                    response.close()

    def test_enrolled_photo_is_local_and_added_to_attendance(self):
        filename = "001_Örnek_Çığdem.png"
        raw = base64.b64decode(synthetic_image().split(",", 1)[1])
        (self.faces_dir / filename).write_bytes(raw)
        manager = FakeFaceManager([{**self.students[0], "filename": filename}])
        application = self.module.create_app(dict(self.config, MODE="recognition"),
                                             face_manager=manager)
        client = application.test_client()
        row = next(s for s in client.get("/api/attendance").get_json()["students"]
                   if s["id"] == "001")
        self.assertEqual(row["photo_url"], "/api/students/001/photo")
        response = client.get(row["photo_url"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, raw)
        self.assertIn("no-store", response.headers["Cache-Control"])
        response.close()
        self.assertEqual(client.get("/api/students/999/photo").status_code, 404)
        self.assertGreaterEqual(client.get(row["photo_url"],
                                          headers={"Host": "attacker.example"}).status_code, 400)

    def test_photo_metadata_cannot_escape_the_reference_directory(self):
        outside = self.directory / "private.png"
        outside.write_bytes(base64.b64decode(synthetic_image().split(",", 1)[1]))
        manager = FakeFaceManager([{**self.students[0], "filename": "../private.png"}])
        application = self.module.create_app(dict(self.config, MODE="recognition"),
                                             face_manager=manager)
        client = application.test_client()
        self.assertEqual(client.get("/api/students/001/photo").status_code, 404)
        row = next(s for s in client.get("/api/attendance").get_json()["students"]
                   if s["id"] == "001")
        self.assertNotIn("photo_url", row)
        self.assertEqual(self.client.get("/static/app.py").status_code, 404)
        self.assertEqual(self.attendance()["stats"]["total"], 2)

    def test_mutation_routes_require_the_session_csrf_token(self):
        for path, payload in [
            ("/api/recognize", {"image": synthetic_image()}),
            ("/api/attendance/toggle", {"id": "001"}),
            ("/api/attendance/reset", {}),
            ("/api/attendance/save", {}),
            ("/api/reload-faces", {}),
        ]:
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path, json=payload).status_code, 403)
                for token in ["incorrect", "ş"]:
                    invalid = dict(self.headers, **{"X-CSRF-Token": token})
                    self.assertEqual(self.client.post(path, json=payload, headers=invalid).status_code, 403)
        self.assertEqual(self.student()["status"], "absent")
        self.assertEqual(list((self.data_dir / "records").glob("*.json")), [])

    def test_foreign_origin_is_rejected_even_with_valid_token(self):
        for origin in ["https://foreign.example", "http://localhost:9999", "null",
                       "http://localhost.attacker.example"]:
            with self.subTest(origin=origin):
                headers = dict(self.headers, Origin=origin)
                response = self.client.post("/api/attendance/toggle", json={"id": "001"}, headers=headers)
                self.assertEqual(response.status_code, 403)
        self.assertEqual(self.student()["status"], "absent")

    def test_untrusted_host_cannot_read_personal_data(self):
        response = self.client.get("/api/attendance", base_url="http://attacker.example")
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("Örnek Öğrenci", response.get_data(as_text=True))

    def test_body_and_student_id_validation_return_client_errors(self):
        for payload in [{}, [], None, {"id": None}, {"id": 1}, {"id": ["001"]},
                        {"id": ""}, {"id": "x" * 65}]:
            with self.subTest(payload=payload):
                self.assertEqual(self.post("/api/attendance/toggle", payload).status_code, 400)
        response = self.client.post("/api/attendance/toggle", data="{broken",
                                    content_type="application/json", headers=self.headers)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.post("/api/attendance/toggle", {"id": "unknown"}).status_code, 404)
        self.assertEqual(self.student()["status"], "absent")

    def test_invalid_images_are_rejected_before_disabled_recognition(self):
        for payload in [{}, [], {"image": 42}, {"image": ""}, {"image": "%%%"},
                        {"image": "data:image/png;base64,%%%"},
                        {"image": "data:image/svg+xml;base64,PHN2Zz48L3N2Zz4="},
                        {"image": synthetic_image(width=4097, height=2)},
                        {"image": base64.b64encode(b"not an image").decode()}]:
            with self.subTest(payload=payload):
                response = self.post("/api/recognize", payload)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.post("/api/recognize", {"image": synthetic_image()}).status_code, 503)

    def test_request_size_limit_returns_json_without_mutating_attendance(self):
        self.app.config["MAX_CONTENT_LENGTH"] = 256
        response = self.post("/api/recognize", {"image": "A" * 512})
        self.assertEqual(response.status_code, 413)
        self.assertIsInstance(response.get_json(), dict)
        self.assertIn("error", response.get_json())
        self.assertEqual(self.attendance()["stats"]["present"], 0)

    def test_marks_are_persisted_and_restored_across_app_restart(self):
        response = self.post("/api/attendance/toggle", {"id": "001"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["student"]["status"], "present")
        self.assertTrue((self.data_dir / "current.json").is_file())
        restarted = self.module.create_app(self.config).test_client()
        saved = self.student(client=restarted)
        self.assertEqual(saved["status"], "present")
        self.assertIsNotNone(saved["time"])
        self.assertFalse(saved["auto"])
        self.assertEqual(self.attendance(restarted)["stats"]["present"], 1)

    def test_roster_refresh_adds_students_and_preserves_marks(self):
        self.assertEqual(self.post("/api/attendance/toggle", {"id": "001"}).status_code, 200)
        self.write_roster([
            {"id": "001", "name": "Örnek Yeni Soyad"}, self.students[1],
            {"id": "003", "name": "Yeni Deneme Öğrencisi"},
        ])
        response = self.post("/api/reload-faces", {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.student()["status"], "present")
        self.assertEqual(self.student()["name"], "Örnek Yeni Soyad")
        self.assertEqual(self.student("003")["status"], "absent")
        self.assertEqual(self.attendance()["stats"]["total"], 3)

    def test_failed_roster_refresh_is_non_destructive(self):
        self.post("/api/attendance/toggle", {"id": "001"})
        before = self.attendance()
        disk_before = (self.data_dir / "current.json").read_bytes()
        for roster in ["{broken", json.dumps([{ "id": "001", "name": "A" },
                                               {"id": "001", "name": "B"}])]:
            with self.subTest(roster=roster):
                (self.data_dir / "students.json").write_text(roster, encoding="utf-8")
                response = self.post("/api/reload-faces", {})
                self.assertGreaterEqual(response.status_code, 400)
                self.assertEqual(self.attendance(), before)
                self.assertEqual((self.data_dir / "current.json").read_bytes(), disk_before)

    def test_removed_roster_student_is_retained_until_archived_reset(self):
        self.post("/api/attendance/toggle", {"id": "001"})
        self.write_roster([self.students[1]])
        self.assertEqual(self.post("/api/reload-faces", {}).status_code, 200)
        self.assertEqual(self.student()["status"], "present")
        self.assertEqual(self.attendance()["stats"]["total"], 2)
        self.assertEqual(self.post("/api/attendance/reset", {}).status_code, 200)
        self.assertEqual([student["id"] for student in self.attendance()["students"]], ["002"])
        snapshot_path = next((self.data_dir / "records").glob("*.json"))
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        self.assertTrue(any(student["id"] == "001" and student["status"] == "present"
                            for student in snapshot["students"]))

    def test_corrupted_current_file_is_preserved_and_startup_fails_explicitly(self):
        path = self.data_dir / "current.json"
        damaged = b"{damaged-current-session"
        path.write_bytes(damaged)
        with self.assertRaises(RuntimeError):
            self.module.create_app(self.config)
        self.assertEqual(path.read_bytes(), damaged)

    def test_failed_atomic_write_and_archive_do_not_clear_memory_or_disk(self):
        self.post("/api/attendance/toggle", {"id": "001"})
        before = self.attendance()
        disk_before = (self.data_dir / "current.json").read_bytes()
        for path, payload in [("/api/attendance/toggle", {"id": "001"}),
                              ("/api/attendance/reset", {})]:
            with self.subTest(path=path):
                with mock.patch("attendance_store.os.replace", side_effect=OSError("synthetic-private-path")):
                    with self.assertLogs(self.app.logger, level="ERROR"):
                        response = self.post(path, payload)
                self.assertEqual(response.status_code, 500)
                self.assertNotIn("synthetic-private-path", response.get_data(as_text=True))
                self.assertEqual(self.attendance(), before)
                self.assertEqual((self.data_dir / "current.json").read_bytes(), disk_before)
                self.assertEqual(list(self.data_dir.rglob("*.pending")), [])

    def test_save_names_are_unique_and_archives_contain_complete_attendance(self):
        self.post("/api/attendance/toggle", {"id": "001"})
        first = self.post("/api/attendance/save", {})
        second = self.post("/api/attendance/save", {})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        filenames = [response.get_json()["filename"] for response in [first, second]]
        self.assertNotEqual(*filenames)
        for filename in filenames:
            snapshot = json.loads((self.data_dir / "records" / filename).read_text(encoding="utf-8"))
            self.assertEqual(snapshot["stats"]["present"], 1)
            self.assertEqual(len(snapshot["students"]), 2)

    def test_reset_archives_previous_marks_before_starting_new_session(self):
        self.post("/api/attendance/toggle", {"id": "001"})
        before = self.attendance()
        self.assertEqual(self.post("/api/attendance/reset", {}).status_code, 200)
        snapshots = list((self.data_dir / "records").glob("*.json"))
        self.assertEqual(len(snapshots), 1)
        snapshot = json.loads(snapshots[0].read_text(encoding="utf-8"))
        self.assertEqual(snapshot["stats"]["present"], 1)
        current = self.attendance()
        self.assertEqual(current["stats"]["present"], 0)
        self.assertNotEqual(current["generation"], before["generation"])
        self.assertIsNone(self.student()["time"])
        restarted = self.module.create_app(self.config).test_client()
        self.assertEqual(self.attendance(restarted)["stats"]["present"], 0)

    def recognition_app(self):
        manager = FakeFaceManager(self.students)
        config = dict(self.config, MODE="recognition")
        app = self.module.create_app(config, face_manager=manager)
        client = app.test_client()
        return app, client, manager, self.session_headers(client)

    def test_recognition_marks_known_student_and_respects_manual_absence(self):
        app, client, manager, headers = self.recognition_app()
        response = client.post("/api/recognize", json={"image": synthetic_image()}, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.student(client=client)["status"], "present")
        self.assertTrue(self.student(client=client)["auto"])
        self.assertEqual(response.get_json()["newly_marked"], [self.students[0]["name"]])
        self.assertEqual(client.post("/api/attendance/toggle", json={"id": "001"}, headers=headers).status_code, 200)
        response = client.post("/api/recognize", json={"image": synthetic_image()}, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["newly_marked"], [])
        self.assertEqual(self.student(client=client)["status"], "absent")
        restarted = self.module.create_app(dict(self.config, MODE="recognition"),
                                           face_manager=FakeFaceManager(self.students)).test_client()
        restart_headers = self.session_headers(restarted)
        self.assertEqual(restarted.post("/api/recognize", json={"image": synthetic_image()},
                                        headers=restart_headers).status_code, 200)
        self.assertEqual(self.student(client=restarted)["status"], "absent")

    def test_stale_generation_cannot_mark_a_reset_session(self):
        app, client, manager, headers = self.recognition_app()
        generation = self.attendance(client)["generation"]
        self.assertEqual(client.post("/api/attendance/reset", json={}, headers=headers).status_code, 200)
        response = client.post("/api/recognize", json={"image": synthetic_image(), "generation": generation},
                               headers=headers)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.student(client=client)["status"], "absent")

    def test_inference_error_preserves_attendance_and_releases_processing_lock(self):
        app, client, manager, headers = self.recognition_app()
        before = self.attendance(client)
        error_class = importlib.import_module("face_manager").FaceRecognitionError
        manager.on_recognize = mock.Mock(side_effect=error_class("synthetic-private-model-path"))
        with self.assertLogs(app.logger, level="ERROR"):
            response = client.post("/api/recognize", json={"image": synthetic_image()}, headers=headers)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("synthetic-private-model-path", response.get_data(as_text=True))
        self.assertEqual(self.attendance(client), before)
        manager.on_recognize = None
        response = client.post("/api/recognize", json={"image": synthetic_image()}, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.student(client=client)["status"], "present")

    def test_reset_during_inference_discards_the_old_frame(self):
        app, client, manager, headers = self.recognition_app()
        reset_client = app.test_client()
        reset_headers = self.session_headers(reset_client)
        inference_started = threading.Event()
        finish_inference = threading.Event()
        outcomes = {}

        def during_inference():
            inference_started.set()
            if not finish_inference.wait(timeout=5):
                raise RuntimeError("Synthetic inference timed out")

        def infer():
            try:
                outcomes["recognition"] = client.post("/api/recognize", json={"image": synthetic_image()},
                                                     headers=headers)
            except Exception as error:
                outcomes["error"] = error

        def reset():
            try:
                outcomes["reset"] = reset_client.post("/api/attendance/reset", json={}, headers=reset_headers)
            except Exception as error:
                outcomes["reset_error"] = error

        manager.on_recognize = during_inference
        recognition_thread = threading.Thread(target=infer, daemon=True)
        reset_thread = threading.Thread(target=reset, daemon=True)
        recognition_thread.start()
        self.assertTrue(inference_started.wait(timeout=5), "Recognition did not reach the synthetic manager")
        reset_thread.start()
        try:
            reset_thread.join(timeout=2)
            self.assertFalse(reset_thread.is_alive(), "Inference blocked attendance reset")
        finally:
            finish_inference.set()
            recognition_thread.join(timeout=5)
            reset_thread.join(timeout=5)
        self.assertNotIn("error", outcomes)
        self.assertNotIn("reset_error", outcomes)
        self.assertEqual(outcomes["reset"].status_code, 200)
        self.assertEqual(outcomes["recognition"].status_code, 409)
        self.assertEqual(self.student(client=reset_client)["status"], "absent")

    def test_pdf_download_handles_turkish_long_names_and_literal_markup(self):
        self.write_roster([
            {"id": "001", "name": "Öğrenci Çığdem <Deneme> & Şahin " * 5},
            {"id": "002", "name": "İpek Ünlü"},
        ])
        self.assertEqual(self.post("/api/reload-faces", {}).status_code, 200)
        response = self.client.get("/api/attendance/pdf")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")
        self.assertTrue(response.data.startswith(b"%PDF-"))
        self.assertIn("attachment", response.headers["Content-Disposition"])
        self.assertGreater(len(response.data), 1000)
        fonts = importlib.import_module("pdf_generator")
        self.assertNotEqual(fonts._register_fonts(), "Helvetica")
        from pypdf import PdfReader
        text = " ".join(page.extract_text() for page in PdfReader(io.BytesIO(response.data)).pages)
        normalized = " ".join(text.split())
        for expected in ["Öğrenci", "Çığdem", "<Deneme>", "Şahin", "İpek Ünlü"]:
            self.assertIn(expected, normalized)
        self.assertNotIn("None", normalized)

    def test_pdf_reports_restored_session_date_instead_of_download_date(self):
        state_path = self.data_dir / "current.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["date"] = "2024-01-02"
        state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        restarted = self.module.create_app(self.config).test_client()
        response = restarted.get("/api/attendance/pdf")
        self.assertEqual(response.status_code, 200)
        from pypdf import PdfReader
        text = " ".join(page.extract_text() for page in PdfReader(io.BytesIO(response.data)).pages)
        self.assertIn("02.01.2024", text)


if __name__ == "__main__":
    unittest.main()
