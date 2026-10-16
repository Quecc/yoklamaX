"""Report pagination and literal text, using only fictional students."""

import io
import unittest

from pypdf import PdfReader

from pdf_generator import generate_pdf


class ReportTests(unittest.TestCase):
    def test_long_roster_repeats_headers_and_retains_all_rows(self):
        students = [
            {"id": str(10000 + number),
             "name": f"Örnek Çığdem <Deneme> & Şahin {number} " + "Uzun Öğrenci İsmi " * 7,
             "status": "present" if number % 2 else "absent", "time": None}
            for number in range(1, 73)
        ]
        stream = io.BytesIO()
        generate_pdf(students, output_path=stream, session_date="2020-02-03")
        reader = PdfReader(stream)
        self.assertGreaterEqual(len(reader.pages), 3)
        text = "\n".join(page.extract_text() for page in reader.pages)
        self.assertIn("03.02.2020", text)
        self.assertIn("Toplam: 72", text)
        self.assertNotIn("None", text)
        for number, page in enumerate(reader.pages, 1):
            page_text = page.extract_text()
            self.assertIn("Öğrenci No", page_text)
            self.assertIn(f"Sayfa {number}", page_text)
        for student in students:
            self.assertIn(student["id"], text)
        self.assertIn("<Deneme> & Şahin", text)


if __name__ == "__main__":
    unittest.main()
