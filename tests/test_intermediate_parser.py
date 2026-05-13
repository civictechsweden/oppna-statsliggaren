import re
import unittest
from pathlib import Path

from bs4 import BeautifulSoup, Tag

from services.intermediate_parser import IntermediateParser


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_RBIDS = [240, 5071, 8103, 8817, 8844, 8899, 21762, 26297]
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
                    elif tag.name == "table":
                        self.assertLessEqual(set(tag.attrs.keys()), {"class"})
                    elif tag.name == "td":
                        self.assertLessEqual(
                            set(tag.attrs.keys()),
                            {"class", "rowspan", "colspan"},
                        )
                    elif tag.name == "th":
                        self.assertLessEqual(
                            set(tag.attrs.keys()),
                            {"rowspan", "colspan", "scope"},
                        )
                    elif tag.name in {"h1", "p"}:
                        self.assertLessEqual(set(tag.attrs.keys()), {"class"})
                    elif tag.name == "sup":
                        self.assertEqual(tag.attrs, {})
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
        self.assertEqual(heading.get("class"), ["document-title"])
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

    def test_word_documenthead_sample_promotes_document_title(self) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(8899))
        soup = BeautifulSoup(xhtml, "html.parser")

        first_heading = soup.find("h1")
        self.assertIsNotNone(first_heading)
        self.assertEqual(
            first_heading.get_text(" ", strip=True),
            "Regleringsbrev för budgetåret 2005 avseende Skogsstyrelsen inom utgiftsområde 23 Jord- och skogsbruk, fiske med anslutande näringar",
        )
        self.assertIsNone(
            soup.find(
                "table",
                string=lambda text: text
                and "Regleringsbrev för budgetåret 2005 avseende Skogsstyrelsen"
                in text,
            )
        )

    def test_word_documenthead_sample_turns_local_numbered_items_into_strong_labels(self) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(8899))
        soup = BeautifulSoup(xhtml, "html.parser")

        self.assertIsNotNone(soup.find("h4", string="1.4 Uppdrag"))
        self.assertIsNone(soup.find(re.compile(r"^h[1-6]$"), string="1. Internationellt arbete"))
        self.assertIsNone(soup.find(re.compile(r"^h[1-6]$"), string="2. Skogsbilvägar"))
        self.assertIsNone(
            soup.find(
                re.compile(r"^h[1-6]$"),
                string="3. Bidrag till miljöorganisationer",
            )
        )

        strong_labels = [
            p.get_text(" ", strip=True)
            for p in soup.find_all("p")
            if p.find("strong")
        ]
        self.assertIn("1. Internationellt arbete", strong_labels)
        self.assertIn("2. Skogsbilvägar", strong_labels)
        self.assertIn("3. Bidrag till miljöorganisationer", strong_labels)
        self.assertIn("Mål", strong_labels)
        self.assertIn("Återrapportering", strong_labels)

    def test_finance_table_footnotes_are_separate_italic_paragraphs(self) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(21762))
        soup = BeautifulSoup(xhtml, "html.parser")

        notes = [
            p.get_text(" ", strip=True)
            for p in soup.find_all("p")
            if p.find("em")
        ]
        self.assertIn("Belopp angivna i tkr", notes)
        self.assertIn(
            "Anslagssparandet prövas efter eventuell omfördelning av anslagssparande",
            notes,
        )
        self.assertIn(
            "Tabellen inkluderar anslagssparande och anslagskredit som i förekommande fall disponeras enligt 7 och 8 §§ anslagsförordningen (2011:223)",
            notes,
        )
        self.assertNotIn(
            "Belopp angivna i tkrAnslagssparandet prövas efter eventuell omfördelning av anslagssparandeTabellen inkluderar anslagssparande och anslagskredit som i förekommande fall disponeras enligt 7 och 8 §§ anslagsförordningen (2011:223)",
            notes,
        )

    def test_numbered_finance_footnotes_preserve_superscripts_and_split_lines(self) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(21762))
        soup = BeautifulSoup(xhtml, "html.parser")

        target_table = None
        for table in soup.find_all("table"):
            if "Omfördelning från anslag/ap" in table.get_text(" ", strip=True):
                target_table = table
                break

        self.assertIsNotNone(target_table)
        self.assertIsNotNone(target_table.find("sup", string="1"))
        self.assertIsNotNone(target_table.find("sup", string="2"))

        notes = [
            p for p in soup.find_all("p")
            if p.find("em")
            and "nomenklatur" in p.get_text(" ", strip=True)
        ]
        self.assertEqual(len(notes), 2)
        self.assertEqual(notes[0].find("sup").get_text(strip=True), "1")
        self.assertEqual(notes[1].find("sup").get_text(strip=True), "2")
        self.assertIn("2019 års nomenklatur", notes[0].get_text(" ", strip=True))
        self.assertIn("2020 års nomenklatur", notes[1].get_text(" ", strip=True))
        self.assertIn(
            "<td>Omfördelning från anslag/ap<sup>1</sup></td>",
            xhtml,
        )
        self.assertIn(
            "<td>Omfördelning till anslag/ap<sup>2</sup></td>",
            xhtml,
        )

    def test_sectioned_sample_does_not_duplicate_footer(self) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(21762))

        self.assertEqual(xhtml.count("<p>På regeringens vägnar</p>"), 1)
        self.assertEqual(xhtml.count("Matilda Ernkrans"), 1)
        self.assertEqual(xhtml.count("Per Anders Nilsson Strandberg"), 1)
        self.assertEqual(xhtml.count("Kopia till"), 1)

    def test_redundant_break_runs_are_collapsed(self) -> None:
        for rbid in [8102, 21762, 6890]:
            with self.subTest(rbid=rbid):
                xhtml = IntermediateParser.parse_letter_html(load_letter_html(rbid))
                self.assertNotIn("<p><br/><br/>", xhtml)
                self.assertNotIn("<br/><br/>", xhtml)

    def test_body_level_breaks_are_removed(self) -> None:
        for rbid in [5140, 8899, 21762]:
            with self.subTest(rbid=rbid):
                xhtml = IntermediateParser.parse_letter_html(load_letter_html(rbid))
                soup = BeautifulSoup(xhtml, "html.parser")
                self.assertFalse(
                    any(
                        isinstance(child, Tag) and child.name == "br"
                        for child in soup.body.find_all(recursive=False)
                    )
                )

    def test_word_blockbase_footer_is_normalized_to_paragraphs(self) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(5071))
        self.assertIn("<p>På regeringens vägnar</p>", xhtml)
        self.assertIn("<p>Bosse Ringholm</p>", xhtml)
        self.assertIn("<p>Anne Dahl</p>", xhtml)
        self.assertIn("<p>Kopia till:</p>", xhtml)
        self.assertNotIn("<table>", xhtml.split("<p>På regeringens vägnar</p>", 1)[1].split("<p>Kopia till:</p>", 1)[0])

    def test_legacy_table_orphan_labels_are_wrapped_in_paragraphs(self) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(6890))
        self.assertIn("<p><strong>Mål 1</strong></p>", xhtml)
        self.assertIn("<p><em>Generella uppdrag</em></p>", xhtml)

    def test_legacy_table_header_keeps_grouped_blocks(self) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(6890))
        self.assertIn('<table class="letterhead">', xhtml)
        self.assertIn('<td class="letterhead-department">Näringsdepartementet</td>', xhtml)
        self.assertIn('<td class="letterhead-decision">Regeringsbeslut</td>', xhtml)
        self.assertIn('<td class="letterhead-decision-number">II 7</td>', xhtml)
        self.assertIn('<td class="letterhead-date">2003-12-18</td>', xhtml)
        self.assertIn(
            '<td class="letterhead-diary">N2003/8903/RUT<br/>N2003/8532/RUT<br/>N2003/5093/RUT (delvis)</td>',
            xhtml,
        )
        self.assertIn(
            '<td class="letterhead-recipient">Verket för näringslivsutveckling<br/>Liljeholmsvägen 32<br/>117 86 STOCKHOLM</td>',
            xhtml,
        )

    def test_classic_header_uses_letterhead_table(self) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(8103))
        self.assertIn('<table class="letterhead">', xhtml)
        self.assertIn('<td class="letterhead-decision">Regeringsbeslut</td>', xhtml)
        self.assertIn('<td class="letterhead-decision-number">19</td>', xhtml)
        self.assertIn('<td class="letterhead-date">2005-12-20</td>', xhtml)
        self.assertIn(
            '<td class="letterhead-diary">S2004/8931/FH<br/>S2005/6161/FH<br/>S2005/8519/FH m.fl.<br/>Se bilaga 1</td>',
            xhtml,
        )

    def test_word_header_uses_letterhead_table(self) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(8899))
        self.assertIn('<table class="letterhead">', xhtml)
        self.assertIn('<td class="letterhead-decision">Regeringsbeslut</td>', xhtml)
        self.assertIn('<td class="letterhead-decision-number">II 4</td>', xhtml)
        self.assertIn('<td class="letterhead-date">2006-02-23</td>', xhtml)
        self.assertIn('<td class="letterhead-diary">N2006/1131/HUB</td>', xhtml)

    def test_word_documenthead_policy_outline_block_is_split_cleanly(self) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(5140))
        self.assertIn("<p><strong>PO Internationellt utvecklingssamarbete</strong></p>", xhtml)
        self.assertIn(
            "<p><strong><em>VO Internationellt utvecklingssamarbete</em></strong></p>",
            xhtml,
        )
        self.assertIn(
            "<p><em>VG Fredsfrämjande och konfliktförebyggande verksamhet</em></p>",
            xhtml,
        )
        self.assertNotIn("<p><em>-</em></p>", xhtml)
        self.assertNotIn("<p><strong><em>VO</em></strong></p>", xhtml)

    def test_anslag_summary_table_is_merged_for_classic_sample(self) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(8103))
        soup = BeautifulSoup(xhtml, "html.parser")

        title = next(
            (
                p
                for p in soup.find_all("p")
                if p.find("strong")
                and p.get_text(" ", strip=True) == "14:5 Smittskyddsinstitutet (Ramanslag)"
            ),
            None,
        )
        self.assertIsNotNone(title)

        target = None
        for table in soup.find_all("table"):
            if "Disponeras av Smittskyddsinstitutet" in table.get_text(" ", strip=True):
                target = table
                break

        self.assertIsNotNone(target)
        rows = target.find_all("tr", recursive=False) or target.tbody.find_all("tr", recursive=False)
        self.assertEqual(len(rows), 2)
        self.assertIn("Disponeras av Smittskyddsinstitutet", rows[0].get_text(" ", strip=True))
        self.assertIn("ap.1", target.get_text(" ", strip=True))

    def test_anslag_summary_table_is_merged_for_modern_sample(self) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(26297))
        soup = BeautifulSoup(xhtml, "html.parser")

        title = next(
            (
                p
                for p in soup.find_all("p")
                if p.find("strong")
                and p.get_text(" ", strip=True)
                == "2:2 Förebyggande åtgärder mot jordskred och andra naturolyckor (Ramanslag)"
            ),
            None,
        )
        self.assertIsNotNone(title)

        target = None
        for table in soup.find_all("table"):
            if "Disponeras av Myndigheten för civilt försvar" in table.get_text(" ", strip=True):
                target = table
                break

        self.assertIsNotNone(target)
        self.assertIn("Disponeras av Myndigheten för civilt försvar", target.get_text(" ", strip=True))
        self.assertIn("ap.2", target.get_text(" ", strip=True))


if __name__ == "__main__":
    unittest.main()
