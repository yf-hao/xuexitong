import tempfile
import unittest
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from core.utils.attachment_preview import render_attachment_preview


class AttachmentPreviewTests(unittest.TestCase):
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

        self.assertIn("DOCX preview text", result.html)
        self.assertEqual(result.title, "answer.docx")
        self.assertIsInstance(result.warnings, tuple)


if __name__ == "__main__":
    unittest.main()