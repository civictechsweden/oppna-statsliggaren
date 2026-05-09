import unittest
from pathlib import Path

from services.template_classifier import (
    TemplateFamily,
    TemplateVariant,
    classify_letter_template,
)


ROOT = Path(__file__).resolve().parents[1]


def load_letter_html(rbid: int) -> str:
    return (ROOT / "letters" / "html" / f"{rbid}.html").read_text(encoding="utf-8")


class TemplateClassifierTests(unittest.TestCase):
    def test_classifies_8817_as_legacy_r_villkor(self) -> None:
        match = classify_letter_template(load_letter_html(8817))

        self.assertEqual(match.family, TemplateFamily.LEGACY)
        self.assertEqual(match.variant, TemplateVariant.LEGACY_R_VILLKOR)

    def test_classifies_240_as_legacy_table(self) -> None:
        match = classify_letter_template(load_letter_html(240))

        self.assertEqual(match.family, TemplateFamily.LEGACY)
        self.assertEqual(match.variant, TemplateVariant.LEGACY_TABLE)

    def test_classifies_8103_as_classic_brevhuvud(self) -> None:
        match = classify_letter_template(load_letter_html(8103))

        self.assertEqual(match.family, TemplateFamily.CLASSIC)
        self.assertEqual(match.variant, TemplateVariant.CLASSIC_BREVHUVUD)

    def test_classifies_8844_as_sectioned_early(self) -> None:
        match = classify_letter_template(load_letter_html(8844))

        self.assertEqual(match.family, TemplateFamily.SECTIONED)
        self.assertEqual(match.variant, TemplateVariant.SECTIONED_EARLY)

    def test_classifies_26297_as_sectioned_modern(self) -> None:
        match = classify_letter_template(load_letter_html(26297))

        self.assertEqual(match.family, TemplateFamily.SECTIONED)
        self.assertEqual(match.variant, TemplateVariant.SECTIONED_MODERN)

    def test_classifies_8899_as_word_documenthead(self) -> None:
        match = classify_letter_template(load_letter_html(8899))

        self.assertEqual(match.family, TemplateFamily.WORD)
        self.assertEqual(match.variant, TemplateVariant.WORD_DOCUMENTHEAD)

    def test_classifies_5071_as_word_blockbase(self) -> None:
        match = classify_letter_template(load_letter_html(5071))

        self.assertEqual(match.family, TemplateFamily.WORD)
        self.assertEqual(match.variant, TemplateVariant.WORD_BLOCKBASE)

    def test_8844_and_26297_share_the_same_family(self) -> None:
        early_match = classify_letter_template(load_letter_html(8844))
        modern_match = classify_letter_template(load_letter_html(26297))

        self.assertEqual(early_match.family, modern_match.family)
        self.assertEqual(early_match.family, TemplateFamily.SECTIONED)

    def test_returns_unknown_for_unmatched_html(self) -> None:
        match = classify_letter_template("<section><p>Plain HTML without markers.</p></section>")

        self.assertEqual(match.family, TemplateFamily.UNKNOWN)
        self.assertEqual(match.variant, TemplateVariant.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
