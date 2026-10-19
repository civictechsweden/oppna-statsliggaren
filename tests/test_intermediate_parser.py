import re
import unittest
from pathlib import Path
from xml.etree import ElementTree

from services import html_dom as dom
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
                soup = dom.parse_html(xhtml)

                self.assertIsNotNone(dom.find(soup, "body"))
                self.assertIsNone(dom.find(soup, "img"))

                # Inspect the emitted XML directly: an HTML parser would insert
                # a head element even though it is absent from the XHTML.
                for tag in ElementTree.fromstring(xhtml).iter():
                    self.assertIn(tag.tag, ALLOWED_TAGS)
                    if tag.tag == "a":
                        self.assertLessEqual(set(tag.attrib.keys()), {"href"})
                    elif tag.tag == "table":
                        self.assertLessEqual(set(tag.attrib.keys()), {"class"})
                    elif tag.tag == "td":
                        self.assertLessEqual(
                            set(tag.attrib.keys()),
                            {"class", "rowspan", "colspan"},
                        )
                    elif tag.tag == "th":
                        self.assertLessEqual(
                            set(tag.attrib.keys()),
                            {"rowspan", "colspan", "scope"},
                        )
                    elif tag.tag in {"h1", "p"}:
                        self.assertLessEqual(set(tag.attrib.keys()), {"class"})
                    elif tag.tag == "sup":
                        self.assertEqual(tag.attrib, {})
                    else:
                        self.assertEqual(tag.attrib, {})

    def test_sample_variants_preserve_basic_structure(self) -> None:
        for rbid in SAMPLE_RBIDS:
            with self.subTest(rbid=rbid):
                xhtml = IntermediateParser.parse_letter_html(load_letter_html(rbid))
                soup = dom.parse_html(xhtml)

                self.assertIsNotNone(dom.find(soup, re.compile("^h[1-6]$")))
                self.assertIsNotNone(dom.find(soup, "p"))

    def test_sample_variants_do_not_nest_block_tags_inside_paragraphs(self) -> None:
        blocked_children = {
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "p",
            "table",
            "ul",
            "ol",
        }

        for rbid in SAMPLE_RBIDS:
            with self.subTest(rbid=rbid):
                xhtml = IntermediateParser.parse_letter_html(load_letter_html(rbid))
                soup = dom.parse_html(xhtml)

                for paragraph in dom.find_all(soup, "p"):
                    self.assertFalse(
                        any(
                            child.tag in blocked_children
                            for child in dom.children(paragraph)
                            if dom.is_tag(child)
                        )
                    )

    def test_modern_sectioned_sample_keeps_title(self) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(26297))
        soup = dom.parse_html(xhtml)

        heading = dom.find(soup, "h1")
        self.assertIsNotNone(heading)
        self.assertEqual(dom.get_attr(heading, "class"), ["document-title"])
        self.assertIn(
            "Regleringsbrev för budgetåret 2026 avseende Myndigheten för civilt försvar",
            dom.text(heading, " ", strip=True),
        )

    def test_sample_with_merged_cells_preserves_table_span_attributes(self) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(11373))

        self.assertIn('rowspan="6"', xhtml)
        self.assertIn('colspan="5"', xhtml)

    def test_classic_sample_uses_single_document_title_and_demoted_outline(
        self,
    ) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(8103))
        soup = dom.parse_html(xhtml)

        headings = dom.find_all(
            dom.find(soup, "body"), re.compile(r"^h[1-6]$"), recursive=False
        )
        self.assertGreaterEqual(len(headings), 4)
        self.assertEqual(
            dom.text(headings[0], " ", strip=True),
            "Regleringsbrev för budgetåret 2006 avseende Smittskyddsinstitutet",
        )
        self.assertEqual(headings[0].tag, "h1")
        self.assertEqual(dom.text(headings[1], " ", strip=True), "VERKSAMHET")
        self.assertEqual(headings[1].tag, "h2")

        self.assertIsNotNone(dom.find(soup, "h3", string="1 Verksamhetsstyrning"))
        self.assertIsNotNone(dom.find(soup, "h4", string="1.1 Politikområde Folkhälsa"))

        labels = [
            dom.text(p, " ", strip=True)
            for p in dom.find_all(soup, "p")
            if dom.find(p, "strong")
        ]
        self.assertIn("Mål", labels)
        self.assertIn("Återrapportering", labels)
        self.assertIn("Övrig återrapportering", labels)
        self.assertIn("Jämställdhetsintegrering", labels)
        self.assertIsNone(dom.find(soup, "h5", string="Jämställdhetsintegrering"))

    def test_modern_sample_merges_split_numbered_headings(self) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(26297))
        soup = dom.parse_html(xhtml)

        self.assertIsNotNone(
            dom.find(soup, "h3", string="1 Mål och återrapporteringskrav")
        )
        self.assertIsNotNone(dom.find(soup, "h3", string="2 Organisationsstyrning"))
        self.assertIsNotNone(dom.find(soup, "h3", string="3 Uppdrag"))
        self.assertIsNone(dom.find(soup, re.compile("^h[1-6]$"), string="1"))
        self.assertIsNone(
            dom.find(
                soup,
                re.compile("^h[1-6]$"),
                string="Arbetet med civil beredskap i Nato",
            )
        )
        strong_labels = [
            dom.text(p, " ", strip=True)
            for p in dom.find_all(soup, "p")
            if dom.find(p, "strong")
        ]
        self.assertIn("Arbetet med civil beredskap i Nato", strong_labels)

    def test_italic_strong_labels_preserve_emphasis(self) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(8103))
        soup = dom.parse_html(xhtml)

        label = next(
            (
                strong
                for strong in dom.find_all(soup, "strong")
                if dom.text(strong, " ", strip=True) == "Övrig återrapportering"
            ),
            None,
        )
        self.assertIsNotNone(label)
        self.assertIsNotNone(dom.find(label, "em"))

    def test_word_documenthead_sample_promotes_document_title(self) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(8899))
        soup = dom.parse_html(xhtml)

        first_heading = dom.find(soup, "h1")
        self.assertIsNotNone(first_heading)
        self.assertEqual(
            dom.text(first_heading, " ", strip=True),
            "Regleringsbrev för budgetåret 2005 avseende Skogsstyrelsen inom utgiftsområde 23 Jord- och skogsbruk, fiske med anslutande näringar",
        )
        self.assertIsNone(
            dom.find(
                soup,
                "table",
                string=lambda text: (
                    text
                    and "Regleringsbrev för budgetåret 2005 avseende Skogsstyrelsen"
                    in text
                ),
            )
        )

    def test_word_documenthead_sample_turns_local_numbered_items_into_strong_labels(
        self,
    ) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(8899))
        soup = dom.parse_html(xhtml)

        self.assertIsNotNone(dom.find(soup, "h4", string="1.4 Uppdrag"))
        self.assertIsNone(
            dom.find(soup, re.compile("^h[1-6]$"), string="1. Internationellt arbete")
        )
        self.assertIsNone(
            dom.find(soup, re.compile("^h[1-6]$"), string="2. Skogsbilvägar")
        )
        self.assertIsNone(
            dom.find(
                soup,
                re.compile("^h[1-6]$"),
                string="3. Bidrag till miljöorganisationer",
            )
        )

        strong_labels = [
            dom.text(p, " ", strip=True)
            for p in dom.find_all(soup, "p")
            if dom.find(p, "strong")
        ]
        self.assertIn("1. Internationellt arbete", strong_labels)
        self.assertIn("2. Skogsbilvägar", strong_labels)
        self.assertIn("3. Bidrag till miljöorganisationer", strong_labels)
        self.assertIn("Mål", strong_labels)
        self.assertIn("Återrapportering", strong_labels)

    def test_finance_table_footnotes_are_separate_italic_paragraphs(self) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(21762))
        soup = dom.parse_html(xhtml)

        notes = [
            dom.text(p, " ", strip=True)
            for p in dom.find_all(soup, "p")
            if dom.find(p, "em")
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

    def test_numbered_finance_footnotes_preserve_superscripts_and_split_lines(
        self,
    ) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(21762))
        soup = dom.parse_html(xhtml)

        target_table = None
        for table in dom.find_all(soup, "table"):
            if "Omfördelning från anslag/ap" in dom.text(table, " ", strip=True):
                target_table = table
                break

        self.assertIsNotNone(target_table)
        self.assertIsNotNone(dom.find(target_table, "sup", string="1"))
        self.assertIsNotNone(dom.find(target_table, "sup", string="2"))

        notes = [
            p
            for p in dom.find_all(soup, "p")
            if dom.find(p, "em") and "nomenklatur" in dom.text(p, " ", strip=True)
        ]
        self.assertEqual(len(notes), 2)
        self.assertEqual(dom.text(dom.find(notes[0], "sup"), strip=True), "1")
        self.assertEqual(dom.text(dom.find(notes[1], "sup"), strip=True), "2")
        self.assertIn("2019 års nomenklatur", dom.text(notes[0], " ", strip=True))
        self.assertIn("2020 års nomenklatur", dom.text(notes[1], " ", strip=True))
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
                soup = dom.parse_html(xhtml)
                self.assertFalse(
                    any(
                        dom.is_tag(child) and child.tag == "br"
                        for child in dom.find_all(
                            dom.find(soup, "body"), recursive=False
                        )
                    )
                )

    def test_word_blockbase_footer_is_normalized_to_paragraphs(self) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(5071))
        self.assertIn("<p>På regeringens vägnar</p>", xhtml)
        self.assertIn("<p>Bosse Ringholm</p>", xhtml)
        self.assertIn("<p>Anne Dahl</p>", xhtml)
        self.assertIn("<p>Kopia till:</p>", xhtml)
        self.assertNotIn(
            "<table>",
            xhtml.split("<p>På regeringens vägnar</p>", 1)[1].split(
                "<p>Kopia till:</p>", 1
            )[0],
        )

    def test_legacy_table_orphan_labels_are_wrapped_in_paragraphs(self) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(6890))
        self.assertIn("<p><strong>Mål 1</strong></p>", xhtml)
        self.assertIn("<p><em>Generella uppdrag</em></p>", xhtml)

    def test_legacy_table_header_keeps_grouped_blocks(self) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(6890))
        self.assertIn('<table class="letterhead">', xhtml)
        self.assertIn(
            '<td class="letterhead-department">Näringsdepartementet</td>', xhtml
        )
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
        self.assertIn(
            "<p><strong>PO Internationellt utvecklingssamarbete</strong></p>", xhtml
        )
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
        soup = dom.parse_html(xhtml)

        title = next(
            (
                p
                for p in dom.find_all(soup, "p")
                if dom.find(p, "strong")
                and dom.text(p, " ", strip=True)
                == "14:5 Smittskyddsinstitutet (Ramanslag)"
            ),
            None,
        )
        self.assertIsNotNone(title)

        target = None
        for table in dom.find_all(soup, "table"):
            if "Disponeras av Smittskyddsinstitutet" in dom.text(
                table, " ", strip=True
            ):
                target = table
                break

        self.assertIsNotNone(target)
        rows = dom.find_all(target, "tr", recursive=False) or dom.find_all(
            dom.find(target, "tbody"), "tr", recursive=False
        )
        self.assertEqual(len(rows), 2)
        self.assertIn(
            "Disponeras av Smittskyddsinstitutet", dom.text(rows[0], " ", strip=True)
        )
        self.assertIn("ap.1", dom.text(target, " ", strip=True))

    def test_anslag_summary_table_is_merged_for_modern_sample(self) -> None:
        xhtml = IntermediateParser.parse_letter_html(load_letter_html(26297))
        soup = dom.parse_html(xhtml)

        title = next(
            (
                p
                for p in dom.find_all(soup, "p")
                if dom.find(p, "strong")
                and dom.text(p, " ", strip=True)
                == "2:2 Förebyggande åtgärder mot jordskred och andra naturolyckor (Ramanslag)"
            ),
            None,
        )
        self.assertIsNotNone(title)

        target = None
        for table in dom.find_all(soup, "table"):
            if "Disponeras av Myndigheten för civilt försvar" in dom.text(
                table, " ", strip=True
            ):
                target = table
                break

        self.assertIsNotNone(target)
        self.assertIn(
            "Disponeras av Myndigheten för civilt försvar",
            dom.text(target, " ", strip=True),
        )
        self.assertIn("ap.2", dom.text(target, " ", strip=True))


if __name__ == "__main__":
    unittest.main()
