import unittest
from xml.etree import ElementTree

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
