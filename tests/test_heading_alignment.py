import re
import unittest
from pathlib import Path

from services import html_dom as dom
from services.heading_alignment import align_headings
from services.intermediate_parser import IntermediateParser


def clean(text):
    return " ".join(text.split())


class HeadingAlignmentTests(unittest.TestCase):
    def align(self, content):
        document = dom.parse_html(f"<html><body>{content}</body></html>")
        align_headings(document, clean)
        return document

    def headings(self, document):
        return [(node.tag, clean(dom.text(node, " ", strip=True)))
                for node in dom.find_all(dom.find(document, "body"), re.compile(r"h[1-6]"), recursive=False)]

    def test_named_roles_align_legacy_and_modern_numbering(self):
        for main, child in [
            ("2.1 Anslag", "2.1.1 Tilldelade anslag"),
            ("4 Anslag", "4.1 Tilldelade anslag"),
        ]:
            with self.subTest(main=main):
                document = self.align(f"<h1>Brevet</h1><h1>FINANSIERING</h1><h2>{main}</h2><h3>{child}</h3>")
                self.assertEqual(self.headings(document), [
                    ("h1", "Brevet"), ("h2", "FINANSIERING"),
                    ("h3", main), ("h4", child),
                ])

    def test_generic_labels_do_not_close_their_policy_parent(self):
        document = self.align(
            "<h1>Brevet</h1><h1>VERKSAMHET</h1><h2>1 Verksamhetsstyrning</h2>"
            "<h3>1.1 Politikområde Folkhälsa</h3><h3>Mål</h3><p>Gör detta.</p>"
            "<h3>Återrapportering</h3><p>Redovisa.</p>"
        )
        self.assertEqual(self.headings(document)[-3:], [
            ("h4", "1.1 Politikområde Folkhälsa"), ("h5", "Mål"), ("h5", "Återrapportering")
        ])

    def test_local_numbered_and_named_titles_stay_peers_below_uppdrag(self):
        document = self.align(
            "<h1>Brevet</h1><h1>VERKSAMHET</h1><h2>1.4 Uppdrag</h2>"
            "<h5><em>1. Internationellt arbete</em></h5><p>Genomför.</p>"
            "<h3>Prognoser</h3><p>Redovisa.</p>"
        )
        self.assertEqual(self.headings(document)[-3:], [
            ("h3", "1.4 Uppdrag"), ("h4", "1. Internationellt arbete"), ("h4", "Prognoser")
        ])
        self.assertIsNotNone(dom.find(document, "em"))

    def test_legacy_policy_roles_are_promoted_only_in_policy_section(self):
        document = self.align(
            "<h1>Brevet</h1><p>PO Oförändrad inledning</p>"
            "<h2>VERKSAMHET</h2><h3>1.1 Verksamhetsstyrning</h3>"
            "<p><strong>PO Hälsa</strong></p><p><strong><em>VO Folkhälsa</em></strong></p>"
            "<p><em>VG Sjukdomsförebyggande</em></p><h3>Mål</h3><p>Gör detta.</p>"
        )
        self.assertEqual(self.headings(document)[-4:], [
            ("h4", "PO Hälsa"), ("h5", "VO Folkhälsa"),
            ("h6", "VG Sjukdomsförebyggande"), ("h6", "Mål")
        ])
        self.assertIsNotNone(dom.find(document, "p", string="PO Oförändrad inledning"))

    def test_finance_keeps_appropriation_and_post_in_the_heading_path(self):
        document = self.align(
            "<h1>Brevet</h1><h1>FINANSIERING</h1><h2>4 Anslag</h2>"
            "<h3>4.1 Tilldelade anslag</h3><h3>Utgiftsområde 23 Areella näringar</h3>"
            "<h4>1:14 Livsmedelsverket (Ramanslag)</h4>"
            "<h4>Villkor för anslag 1:14</h4><h4>ap.1 Livsmedelsverket</h4>"
        )
        self.assertEqual(self.headings(document)[-4:], [
            ("h4", "Utgiftsområde 23 Areella näringar"),
            ("h5", "1:14 Livsmedelsverket (Ramanslag)"),
            ("h5", "Villkor för anslag 1:14"), ("h6", "ap.1 Livsmedelsverket")
        ])

    def test_all_seven_templates_keep_headings_content_and_one_document_title(self):
        for ident in [240, 5071, 8899, 8187, 8103, 21762, 25867]:
            with self.subTest(rbid=ident):
                raw = Path(f"letters/html/{ident}.html").read_text(encoding="utf-8")
                document = dom.parse_html(IntermediateParser.parse_letter_html(raw))
                before = clean(dom.text(document, " ", strip=True))
                count = len(self.headings(document))
                align_headings(document, IntermediateParser._clean_text)
                headings = self.headings(document)
                self.assertEqual(clean(dom.text(document, " ", strip=True)), before)
                self.assertGreaterEqual(len(headings), count)
                self.assertEqual(sum(tag == "h1" for tag, _ in headings), 1)
                align_headings(document, IntermediateParser._clean_text)
                self.assertEqual(self.headings(document), headings)

    def test_other_major_divisions_are_not_additional_document_titles(self):
        document = self.align("<h1>Brevet</h1><h1>ÖVRIGA BESTÄMMELSER</h1><p>Villkor.</p>")
        self.assertEqual(self.headings(document), [("h1", "Brevet"), ("h2", "ÖVRIGA BESTÄMMELSER")])

    def test_numbered_siblings_and_children_follow_their_semantic_parent(self):
        document = self.align(
            "<h1>Brevet</h1><h2>1 VERKSAMHET</h2><h3>1.4 Uppdrag</h3>"
            "<h5>1.5 Fristående återrapportering</h5>"
            "<h5>1.5.1 Första delområdet</h5><h5>1.5.2 Andra delområdet</h5>"
            "<h2>6 Avgifter och bidrag</h2><h4>6.1 Beräknad budget</h4>"
        )
        self.assertEqual(self.headings(document)[-5:], [
            ("h3", "1.5 Fristående återrapportering"),
            ("h4", "1.5.1 Första delområdet"), ("h4", "1.5.2 Andra delområdet"),
            ("h2", "6 Avgifter och bidrag"), ("h3", "6.1 Beräknad budget")
        ])

    def test_uo_resets_generic_label_parent_and_combined_post_is_deepest(self):
        document = self.align(
            "<h1>Brevet</h1><h2>FINANSIERING</h2><h3>4 Anslag</h3>"
            "<h4>4.3 Finansiella villkor</h4><h5>4.3.5 Beställningsbemyndiganden</h5>"
            "<h4>Utgiftsområde 23 Areella näringar</h4><h6>Villkor</h6>"
            "<h5>41:2 Insatser för skogsbruket</h5><h5>41:2 ap.1 Bidrag till skogsbruket</h5>"
        )
        self.assertEqual(self.headings(document)[-3:], [
            ("h5", "Villkor"), ("h5", "41:2 Insatser för skogsbruket"),
            ("h6", "41:2 ap.1 Bidrag till skogsbruket")
        ])
