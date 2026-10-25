import tempfile
import unittest
import fitz
import base64
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from core.utils.attachment_preview import (
    extract_attachment_scoring_content,
    extract_attachment_text,
    render_attachment_preview,
)


class AttachmentPreviewTests(unittest.TestCase):
    def test_extracts_code_and_markdown_as_plain_text(self):
        with tempfile.TemporaryDirectory() as folder:
            code_path = Path(folder) / "answer.py"
            code_path.write_text("def answer(): return 42", encoding="utf-8")
            markdown_path = Path(folder) / "answer.md"
            markdown_path.write_text(
                "# Answer\n\nThe result is 42.", encoding="utf-8"
            )

            self.assertEqual(
                extract_attachment_text(code_path),
                "def answer(): return 42",
            )
            self.assertEqual(
                extract_attachment_text(markdown_path),
                "# Answer\n\nThe result is 42.",
            )

    def test_preview_html_has_light_and_dark_theme_styles(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "main.py"
            path.write_text("def answer():\n    return 42\n", encoding="utf-8")
            document = render_attachment_preview(path)

        self.assertIn("--preview-bg:", document.html)
        self.assertIn('body[data-theme="light"] .highlight', document.html)
        self.assertIn('body[data-theme="dark"] .highlight', document.html)

    def test_highlights_multiple_programming_languages(self):
        for filename, source, keyword_token in (
            ("Main.java", "class Main { int answer = 42; }", "kd"),
            ("main.py", "def answer():\n    return 42\n", "k"),
            ("main.rs", "fn answer() -> i32 { 42 }", "k"),
        ):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / filename
                path.write_text(source, encoding="utf-8")
                document = render_attachment_preview(path)
                self.assertIn("class=\"highlight\"", document.html)
                self.assertIn(f'class="{keyword_token}"', document.html)

    def test_unknown_extension_falls_back_to_plain_text(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "notes.txt"
            path.write_text("ordinary text", encoding="utf-8")
            document = render_attachment_preview(path)

        self.assertIn("ordinary text", document.html)
        self.assertNotIn("class=\"k\"", document.html)

    def test_markdown_is_rendered_and_unsafe_html_is_removed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "README.md"
            path.write_text(
                "# Preview\n\n<script>alert(1)</script>\n\n"
                "```python\ndef answer():\n    return 42\n```\n",
                encoding="utf-8",
            )
            document = render_attachment_preview(path)

        self.assertIn("<h1>Preview</h1>", document.html)
        self.assertNotIn("<script", document.html.lower())
        self.assertIn("class=\"highlight\"", document.html)

    def test_docx_is_rendered_as_html_and_reports_conversion_messages(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "answer.docx"
            with ZipFile(path, "w", ZIP_DEFLATED) as document:
                document.writestr(
                    "[Content_Types].xml",
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                    '<Default Extension="xml" ContentType="application/xml"/>'
                    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                    '</Types>',
                )
                document.writestr(
                    "_rels/.rels",
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                    '</Relationships>',
                )
                document.writestr(
                    "word/document.xml",
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                    '<w:body><w:p><w:r><w:t>DOCX preview text</w:t></w:r></w:p>'
                    '<w:sectPr/></w:body></w:document>',
                )

            result = render_attachment_preview(path)
            extracted_text = extract_attachment_text(path)

        self.assertIn("DOCX preview text", result.html)
        self.assertIn("DOCX preview text", extracted_text)
        self.assertEqual(result.title, "answer.docx")
        self.assertIsInstance(result.warnings, tuple)

    def test_docx_scoring_extracts_text_and_embedded_images_together(self):
        image_data_uri = (
            "data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/"
            "iZk9HQAAAABJRU5ErkJggg=="
        )
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "answer.docx"
            path.write_bytes(b"docx")
            mammoth_result = SimpleNamespace(
                value=(
                    f"<p>前面的正文</p><img src=\"{image_data_uri}\">"
                    "<p>后续正文</p>"
                )
            )
            with patch(
                "core.utils.attachment_preview.mammoth.convert_to_html",
                return_value=mammoth_result,
            ):
                text, images = extract_attachment_scoring_content(path)

        self.assertIn("前面的正文", text)
        self.assertIn("[图片 1]", text)
        self.assertIn("后续正文", text)
        self.assertEqual(images, (image_data_uri,))

    def test_scoring_accepts_standalone_image_attachments(self):
        image_data_uri = (
            "data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/"
            "iZk9HQAAAABJRU5ErkJggg=="
        )
        encoded = image_data_uri.split(",", 1)[1]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "answer.png"
            path.write_bytes(base64.b64decode(encoded))

            text, images = extract_attachment_scoring_content(path)

        self.assertEqual(text, "")
        self.assertEqual(images, (image_data_uri,))

    def test_scoring_rejects_invalid_standalone_image_attachments(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "answer.png"
            path.write_bytes(b"not a png")

            with self.assertRaisesRegex(ValueError, "格式无效或不受支持"):
                extract_attachment_scoring_content(path)


class PdfAttachmentTests(unittest.TestCase):
    @staticmethod
    def make_pdf(path, text=None, pages=1, password=None):
        document = fitz.open()
        for _ in range(pages):
            page = document.new_page()
            if text:
                page.insert_text((72, 72), text)
            else:
                page.draw_rect(fitz.Rect(50, 50, 200, 200), fill=(0, 0, 0))
        if password:
            document.save(
                str(path), encryption=fitz.PDF_ENCRYPT_AES_256,
                user_pw=password, owner_pw=password,
            )
        else:
            document.save(str(path))
        document.close()

    def test_text_pdf_is_scored_as_text(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "a.pdf"
            self.make_pdf(path, "Answer: the quick brown fox jumps over it")
            text, images = extract_attachment_scoring_content(path)
            self.assertIn("第 1 页", text)
            self.assertIn("quick brown fox", text)
            self.assertEqual(images, ())
            self.assertIn("quick brown fox", render_attachment_preview(path).html)

    def test_scanned_pdf_is_scored_as_images_and_page_limited(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "scan.pdf"
            self.make_pdf(path, pages=12)
            text, images = extract_attachment_scoring_content(path)
            self.assertEqual(len(images), 10)
            self.assertIn("共 12 页", text)
            self.assertTrue(images[0].startswith("data:image/png;base64,"))
            preview = render_attachment_preview(path)
            self.assertIn("<img", preview.html)
            self.assertTrue(preview.warnings)

    def test_encrypted_and_broken_pdf_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            encrypted = Path(folder) / "enc.pdf"
            self.make_pdf(encrypted, "secret text here", password="pw")
            with self.assertRaisesRegex(ValueError, "加密"):
                extract_attachment_scoring_content(encrypted)
            broken = Path(folder) / "bad.pdf"
            broken.write_bytes(b"not a pdf")
            with self.assertRaisesRegex(ValueError, "无法打开"):
                render_attachment_preview(broken)


if __name__ == "__main__":
    unittest.main()