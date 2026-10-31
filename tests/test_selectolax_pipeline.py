import unittest
from xml.etree import ElementTree

import mdformat
from markdownify import markdownify

from services.cleaner import Cleaner
from services.intermediate_parser import IntermediateParser


class SelectolaxPipelineTests(unittest.TestCase):
    def parse(self, content):
        source = (
            '<div id="BrevHuvud"><div class="avs">Finansdepartementet</div></div>'
            '<div id="RegleringsbrevBody">'
            '<div id="BrevInledandeText_Rubrik">Regleringsbrev för Övningsmyndigheten</div>'
            f"{content}</div>"
        )
        xhtml = IntermediateParser.parse_letter_html(source)
        return xhtml, ElementTree.fromstring(xhtml)

    def test_preserves_sibling_fragments_links_entities_and_table_spans(self):
        xhtml, document = self.parse(
            "<h2>VERKSAMHET</h2><p>Åtgärder &amp; mål "
            '<a href="https://example.org/?a=1&amp;b=2">länk</a>.</p>'
            '<table><tr><th colspan="2">Rubrik</th></tr>'
            '<tr><td rowspan="2">Örebro</td><td>1</td></tr>'
            "<tr><td>2</td></tr></table>"
            "<p>Slutet.</p><!-- discard this comment --><script>noise()</script>"
        )
        self.assertEqual(
            document.find('.//td[@class="letterhead-department"]').text,
            "Finansdepartementet",
        )
        self.assertEqual(
            document.find(".//h1").text, "Regleringsbrev för Övningsmyndigheten"
        )
        self.assertEqual(
            document.find(".//a").attrib["href"], "https://example.org/?a=1&b=2"
        )
        self.assertIsNotNone(document.find('.//th[@colspan="2"]'))
        self.assertIsNotNone(document.find('.//td[@rowspan="2"]'))
        self.assertIn("Slutet.", "".join(document.itertext()))
        self.assertNotIn("noise", xhtml)
        self.assertNotIn("discard this comment", xhtml)

    def test_preserves_footnote_markers_and_splits_lines(self):
        _, document = self.parse(
            '<div class="fotnot"><sup>1</sup> Första noten.<br/>'
            "<sup>2</sup> Andra noten.</div>"
        )
        notes = document.findall(".//p/em")
        self.assertEqual([note.find("sup").text for note in notes], ["1", "2"])
        self.assertEqual(
            ["".join(note.itertext()) for note in notes],
            ["1Första noten.", "2Andra noten."],
        )

    def test_unwraps_legacy_namespace_elements(self):
        _, document = self.parse("<r:villkor><p>Ett villkor.</p></r:villkor>")
        self.assertIn("Ett villkor.", "".join(document.itertext()))
        self.assertTrue(all(":" not in node.tag for node in document.iter()))

    def test_html_cleaner_keeps_heading_and_paragraph_continuations(self):
        html = Cleaner.clean_letter_html(
            '<div><div class="header-div"><h2>1</h2><h2>Uppdrag</h2></div>'
            "<p>1. Första delen</p><p>fortsättningen<sup>2</sup></p></div>"
        )
        self.assertIn("<h2>1 Uppdrag</h2>", html)
        self.assertIn("<p>1. Första delen fortsättningen[2]</p>", html)

    def test_nested_intro_is_flattened_without_losing_text(self):
        _, document = self.parse(
            '<div id="BrevInledandeText_InledandeText"><div>'
            "<p>Regeringen beslutar att följande ska gälla.</p>"
            "</div></div><h2>VERKSAMHET</h2>"
        )
        self.assertIsNone(document.find(".//p/p"))
        self.assertIn(
            "Regeringen beslutar att följande ska gälla.",
            ["".join(paragraph.itertext()) for paragraph in document.iter("p")],
        )

    def test_underlined_label_stays_inside_its_paragraph(self):
        _, document = self.parse(
            "<p><strong><u>Tillgängligt transportsystem</u></strong></p>"
        )
        self.assertIsNone(document.find(".//p/p"))
        self.assertIn(
            "Tillgängligt transportsystem",
            ["".join(label.itertext()) for label in document.iter("strong")],
        )

    def test_nested_strong_does_not_duplicate_markdown_markers(self):
        xhtml, document = self.parse(
            "<p><strong><strong>Andra uppdraget</strong></strong></p>"
        )
        self.assertIsNone(document.find(".//strong/strong"))
        markdown = Cleaner.clean_markdown(
            mdformat.text(
                markdownify(xhtml, heading_style="ATX"), options={"number": True}
            )
        )
        self.assertIn("**Andra uppdraget**", markdown)
        self.assertNotIn("****Andra uppdraget****", markdown)

    def test_inline_source_markup_does_not_wrap_block_headings(self):
        _, document = self.parse(
            "<p>Inledning.<em /></p>"
            '<div><div class="header-div"><span><h2>4</h2></span>'
            "<span><h2>Anslag</h2></span></div></div>"
        )
        for container in document.iter():
            if container.tag not in {"p", "em", "strong"}:
                continue
            self.assertFalse(
                any(
                    heading.tag in {"h1", "h2", "h3", "h4", "h5", "h6"}
                    for heading in container.iter()
                    if heading is not container
                )
            )
        self.assertIn(
            "4 Anslag", ["".join(heading.itertext()) for heading in document.iter("h3")]
        )

    def test_split_finance_heading_and_allocation_tables_are_normalized(self):
        xhtml, document = self.parse(
            "<div><h1>FINANSIERING</h1></div>"
            '<div><div class="header-div"><span><h2>4</h2></span>'
            "<span><h2>Anslag</h2></span></div></div>"
            '<div><div class="header-div"><span><h3>4.1</h3></span>'
            "<span><h3>Tilldelade anslag/anslagsposter (belopp angivna i tkr)</h3>"
            "</span></div></div>"
            '<div><div class="header-div a6"><span><h4>1:4</h4></span>'
            "<span><h4>Övningsmyndigheten (Ramanslag)</h4></span></div></div>"
            '<div><table class="table-anslagtilldelade-myndighet"><thead><tr>'
            "<th>Disponeras av Övningsmyndigheten</th><th>100</th>"
            "</tr></thead></table></div>"
            '<table class="table-anslagtilldelade-anslagspost-ap"><thead>'
            '<tr class="invisible-header"><th>Nomenklatur</th><th>Namn</th>'
            "<th>Belopp</th></tr></thead><tbody><tr><td>ap.1</td>"
            "<td>Förvaltning</td><td>100</td></tr></tbody></table>"
        )
        self.assertIsNone(document.find(".//p/h3"))
        self.assertIsNone(document.find(".//p/h4"))
        self.assertIn(
            "4.1 Tilldelade anslag/anslagsposter (belopp angivna i tkr)",
            ["".join(heading.itertext()) for heading in document.iter("h4")],
        )

        tables = [
            table
            for table in document.iter("table")
            if "Disponeras av Övningsmyndigheten" in "".join(table.itertext())
        ]
        self.assertEqual(len(tables), 1)
        self.assertEqual(
            [
                [" ".join("".join(cell.itertext()).split()) for cell in row]
                for row in tables[0].iter("tr")
            ],
            [
                ["Nomenklatur", "Namn", "Belopp"],
                ["Disponeras av Övningsmyndigheten", "100"],
                ["ap.1", "Förvaltning", "100"],
            ],
        )
        markdown = Cleaner.clean_markdown(
            mdformat.text(
                markdownify(xhtml, heading_style="ATX"), options={"number": True}
            )
        )
        self.assertIn("#### 4.1 Tilldelade anslag/anslagsposter", markdown)
        self.assertIn("| Disponeras av Övningsmyndigheten | | 100 |", markdown)

    def test_html_cleaner_keeps_rows_in_combined_allocation_table(self):
        html = Cleaner.clean_letter_html(
            '<table class="table-anslagtilldelade-myndighet"><tr>'
            "<th>Disponeras av Övningsmyndigheten</th><th>100</th></tr></table>"
            '<table class="table-anslagtilldelade-anslagspost-ap">'
            '<tr class="invisible-header"><th>Nomenklatur</th><th>Namn</th>'
            "<th>Belopp</th></tr><tr><td>ap.1</td><td>Förvaltning</td>"
            "<td>100</td></tr></table>"
        )
        document = ElementTree.fromstring(html)
        tables = list(document.iter("table"))
        self.assertEqual(len(tables), 1)
        self.assertIn("ap.1", "".join(tables[0].itertext()))
