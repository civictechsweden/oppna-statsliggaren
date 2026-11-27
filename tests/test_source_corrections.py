import unittest
from pathlib import Path
from xml.etree import ElementTree

from services import html_dom as dom
from services.intermediate_parser import IntermediateParser
from services.source_corrections import (
    CORRECTIONS, TITLE_REPLACEMENTS, correct_document, correct_markup,
    correct_metadata_title,
)


class SourceCorrectionTests(unittest.TestCase):
    def test_markup_repairs_are_recorded_and_idempotent(self):
        applied = []
        result = correct_markup('<p>Före<em />efter\x08</p>', applied)
        self.assertEqual(result, '<p>Före<em ></em>efter</p>')
        self.assertEqual(applied, ['empty-emphasis', 'invalid-xml-characters'])
        second = []
        self.assertEqual(correct_markup(result, second), result)
        self.assertEqual(second, [])

    def test_all_exact_metadata_repairs_have_a_ledger_entry(self):
        for before, after in TITLE_REPLACEMENTS:
            applied = []
            self.assertEqual(correct_metadata_title(before, applied), after)
            self.assertEqual(applied, ['metadata-category'])
            self.assertTrue(all(key in CORRECTIONS for key in applied))

    def test_unique_title_introduction_is_not_discarded(self):
        source = dom.parse_html(
            '<div id="BrevInledandeText_Rubrik">Regleringsbrev för Test '
            '<br>Regeringen beslutar att följande ska gälla.</div>'
        )
        applied = []
        correct_document(source, applied)
        self.assertIn('Regeringen beslutar', dom.text(source))
        self.assertEqual(applied, [])

    def test_confirmed_duplicate_is_removed_only_from_title(self):
        raw = Path('letters/html/21417.html').read_text()
        applied = []
        result = IntermediateParser.parse_letter_html(raw, corrections=applied)
        document = ElementTree.fromstring(result)
        self.assertEqual(document.find('.//{http://www.w3.org/1999/xhtml}h1').text,
                         'Regleringsbrev för budgetåret 2021 avseende Statens skolinspektion')
        self.assertIn('Regeringen beslutar att följande', ''.join(document.itertext()))
        self.assertIn('duplicated-title-introduction', applied)

    def test_heading_typo_is_corrected_without_touching_quoted_prose(self):
        source = dom.parse_html('<h4>Återrrapportering</h4><p>Återrrapportering</p>')
        applied = []
        correct_document(source, applied)
        self.assertEqual(dom.text(dom.find(source, 'h4')), 'Återrapportering')
        self.assertEqual(dom.text(dom.find(source, 'p')), 'Återrrapportering')
        self.assertEqual(applied, ['reporting-heading-spelling'])
