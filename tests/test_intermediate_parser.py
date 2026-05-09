import re
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

from services.intermediate_parser import IntermediateParser


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_RBIDS = [240, 5071, 8103, 8817, 8844, 8899, 26297]
ALLOWED_TAGS = IntermediateParser.ALLOWED_TAGS


def load_letter_html(rbid: int) -> str:
    return (ROOT / "letters" / "html" / f"{rbid}.html").read_text(encoding="utf-8")


class IntermediateParserTests(unittest.TestCase):
    def test_sample_variants_use_only_allowed_tags_and_attributes(self) -> None:
        for rbid in SAMPLE_RBIDS:
            with self.subTest(rbid=rbid):
                xhtml = IntermediateParser.parse_letter_html(load_letter_html(rbid))
                soup = BeautifulSoup(xhtml, "html.parser")

                self.assertIsNotNone(soup.find("body"))
                self.assertIsNone(soup.find("img"))

                for tag in soup.find_all(True):
                    self.assertIn(tag.name, ALLOWED_TAGS)
                    if tag.name == "a":
                        self.assertLessEqual(set(tag.attrs.keys()), {"href"})
                    elif tag.name == "td":
                        self.assertLessEqual(set(tag.attrs.keys()), {"rowspan", "colspan"})
                    elif tag.name == "th":
                        self.assertLessEqual(
                            set(tag.attrs.keys()),
                            {"rowspan", "colspan", "scope"},
                        )
                    else:
                        self.assertEqual(tag.attrs, {})

    def test_sample_variants_preserve_basic_structure(self) -> None:
        for rbid in SAMPLE_RBIDS:
            with self.subTest(rbid=rbid):
                xhtml = IntermediateParser.parse_letter_html(load_letter_html(rbid))
                soup = BeautifulSoup(xhtml, "html.parser")

                self.assertIsNotNone(soup.find(re.compile(r"^h[1-6]$")))
                self.assertIsNotNone(soup.find("p"))

    def test_sample_variants_do_not_nest_block_tags_inside_paragraphs(self) -> None:
        blocked_children = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "table", "ul", "ol"}

        for rbid in SAMPLE_RBIDS:
            with self.subTest(rbid=rbid):
                xhtml = IntermediateParser.parse_letter_html(load_letter_html(rbid))
                soup = BeautifulSoup(xhtml, "html.parser")

                for paragraph in soup.find_all("p"):
                    self.assertFalse(
                        any(
                            child.name in blocked_children
                            for child in paragraph.children
                            if getattr(child, "name", None)
                        )
                    )

    def test_modern_sectioned_sample_keeps_title(self) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(26297))
        soup = BeautifulSoup(xhtml, "html.parser")

        heading = soup.find("h1")
        self.assertIsNotNone(heading)
        self.assertIn(
            "Regleringsbrev för budgetåret 2026 avseende Myndigheten för civilt försvar",
            heading.get_text(" ", strip=True),
        )

    def test_sample_with_merged_cells_preserves_table_span_attributes(self) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(11373))

        self.assertIn('rowspan="6"', xhtml)
        self.assertIn('colspan="5"', xhtml)

    def test_classic_sample_uses_single_document_title_and_demoted_outline(self) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(8103))
        soup = BeautifulSoup(xhtml, "html.parser")

        headings = soup.body.find_all(re.compile(r"^h[1-6]$"), recursive=False)
        self.assertGreaterEqual(len(headings), 4)
        self.assertEqual(
            headings[0].get_text(" ", strip=True),
            "Regleringsbrev för budgetåret 2006 avseende Smittskyddsinstitutet",
        )
        self.assertEqual(headings[0].name, "h1")
        self.assertEqual(headings[1].get_text(" ", strip=True), "VERKSAMHET")
        self.assertEqual(headings[1].name, "h2")

        self.assertIsNotNone(soup.find("h3", string="1 Verksamhetsstyrning"))
        self.assertIsNotNone(
            soup.find("h4", string="1.1 Politikområde Folkhälsa")
        )

        labels = [
            p.get_text(" ", strip=True)
            for p in soup.find_all("p")
            if p.find("strong")
        ]
        self.assertIn("Mål", labels)
        self.assertIn("Återrapportering", labels)
        self.assertIn("Övrig återrapportering", labels)
        self.assertIn("Jämställdhetsintegrering", labels)
        self.assertIsNone(soup.find("h5", string="Jämställdhetsintegrering"))

    def test_modern_sample_merges_split_numbered_headings(self) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(26297))
        soup = BeautifulSoup(xhtml, "html.parser")

        self.assertIsNotNone(soup.find("h3", string="1 Mål och återrapporteringskrav"))
        self.assertIsNotNone(soup.find("h3", string="2 Organisationsstyrning"))
        self.assertIsNotNone(soup.find("h3", string="3 Uppdrag"))
        self.assertIsNone(soup.find(re.compile(r"^h[1-6]$"), string="1"))
        self.assertIsNone(
            soup.find(
                re.compile(r"^h[1-6]$"),
                string="Arbetet med civil beredskap i Nato",
            )
        )
        strong_labels = [
            p.get_text(" ", strip=True)
            for p in soup.find_all("p")
            if p.find("strong")
        ]
        self.assertIn("Arbetet med civil beredskap i Nato", strong_labels)

    def test_italic_strong_labels_preserve_emphasis(self) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(8103))
        soup = BeautifulSoup(xhtml, "html.parser")

        label = next(
            (
                strong
                for strong in soup.find_all("strong")
                if strong.get_text(" ", strip=True) == "Övrig återrapportering"
            ),
            None,
        )
        self.assertIsNotNone(label)
        self.assertIsNotNone(label.find("em"))


if __name__ == "__main__":
    unittest.main()
