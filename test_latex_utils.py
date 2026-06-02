import unittest

from core.utils.latex_utils import apply_latex_unicode_map, is_simple_unicode, latex_to_unicode


class LatexUtilsTests(unittest.TestCase):
    def test_mathbb_common_sets_convert_to_unicode(self):
        cases = {
            r"\mathbb{N}": "ℕ",
            r"\mathbb{Z}": "ℤ",
            r"\mathbb{Q}": "ℚ",
            r"\mathbb{R}": "ℝ",
            r"\mathbb{C}": "ℂ",
            r"\mathbb{P}": "ℙ",
            r"\mathbb{H}": "ℍ",
        }

        for latex, expected in cases.items():
            with self.subTest(latex=latex):
                self.assertEqual(apply_latex_unicode_map(latex), expected)
                self.assertTrue(is_simple_unicode(expected))

    def test_mathbb_does_not_convert_unknown_symbols(self):
        self.assertEqual(apply_latex_unicode_map(r"\mathbb{A}"), r"\mathbb{A}")
        self.assertEqual(apply_latex_unicode_map(r"\mathbb{ABC}"), r"\mathbb{ABC}")

    def test_question_upload_mathbb_pipeline_returns_simple_unicode(self):
        expr = latex_to_unicode(r"\mathbb{N}")
        expr = apply_latex_unicode_map(expr)

        self.assertEqual(expr, "ℕ")
        self.assertTrue(is_simple_unicode(expr))

    def test_question_upload_simple_operator_pipeline(self):
        cases = {
            r"*": "*",
            r"\circ": "∘",
            r"R_1 \circ R_2": "R₁ ∘ R₂",
        }

        for latex, expected in cases.items():
            with self.subTest(latex=latex):
                expr = latex_to_unicode(latex)
                expr = apply_latex_unicode_map(expr)

                self.assertEqual(expr, expected)
                self.assertTrue(is_simple_unicode(expr))


if __name__ == "__main__":
    unittest.main()
