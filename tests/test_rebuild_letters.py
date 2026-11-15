import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree

import pyarrow as pa
import pyarrow.parquet as pq

from scripts import rebuild_letters
from services.intermediate_parser import IntermediateParser


HTML = (
    '<div id="BrevHuvud"><div class="avs">Finansdepartementet</div></div>'
    '<div id="RegleringsbrevBody">'
    '<div id="BrevInledandeText_Rubrik">Regleringsbrev för Övningsmyndigheten</div>'
    '<h2>VERKSAMHET</h2><h2>3 Uppdrag</h2>'
    '<h4 class="italic">5. Ett särskilt uppdrag</h4>'
    '<p>Myndigheten ska redovisa sitt arbete.</p>'
    '<table><tr><th colspan="2">Fördelning</th></tr>'
    '<tr><td>Förvaltning</td><td>100</td></tr></table></div>'
)


class RebuildLettersTests(unittest.TestCase):
    def snapshot(self, path):
        schema = pa.schema([
            pa.field("id", pa.int64(), metadata={b"identity": b"RBID"}),
            pa.field("name", pa.string()),
            pa.field("original_rbid", pa.int64()),
            pa.field("expenditure_areas", pa.list_(pa.int16())),
            pa.field("html", pa.string()),
            pa.field("xhtml", pa.string()),
            pa.field("md", pa.string()),
        ], metadata={b"snapshot": b"pinned-test-revision"})
        rows = [
            {"id": 20, "name": "Övningsmyndigheten", "original_rbid": 10,
             "expenditure_areas": [2, 7], "html": HTML, "xhtml": "stale", "md": "stale"},
            {"id": 10, "name": "Årsmyndigheten", "original_rbid": None,
             "expenditure_areas": [], "html": HTML, "xhtml": "old", "md": "old"},
        ]
        pq.write_table(pa.Table.from_pylist(rows, schema=schema), path)
        return pq.read_table(path)

    def test_rebuild_preserves_original_fields_schema_order_and_reports_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output, audit = root / "source.parquet", root / "output.parquet", root / "audit.json"
            before = self.snapshot(source)
            source_bytes = source.read_bytes()
            report = rebuild_letters.rebuild(source, output, report_path=audit, workers=1, batch_size=1)
            after = pq.read_table(output)
            untouched = [name for name in before.schema.names if name not in {"xhtml", "md"}]
            self.assertTrue(before.select(untouched).equals(after.select(untouched)))
            self.assertTrue(before.schema.equals(after.schema, check_metadata=True))
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(after["id"].to_pylist(), [20, 10])
            for row in after.to_pylist():
                document = ElementTree.fromstring(row["xhtml"])
                self.assertIsNotNone(document.find('.//th[@colspan="2"]'))
                self.assertIn("5. Ett särskilt uppdrag", row["md"])
                self.assertIn("Myndigheten ska redovisa sitt arbete.", row["md"])
                self.assertNotIn("stale", row["md"])
            self.assertEqual(report["rows"], 2)
            self.assertEqual(report["changed"], {"xhtml": 2, "md": 2})
            self.assertTrue(report["original_fields_unchanged"])
            self.assertEqual(report["source_sha256"], hashlib.sha256(source_bytes).hexdigest())
            self.assertEqual(report["output_sha256"], hashlib.sha256(output.read_bytes()).hexdigest())
            saved = json.loads(audit.read_text())
            self.assertEqual(saved["rows"], 2)
            self.assertEqual(sum(saved["heading_counts"].values()), sum(report["heading_counts"].values()))

    def test_correction_ids_are_counted_and_linked_to_letters(self):
        original_parser = IntermediateParser.parse_letter_html

        def corrected(html, *, corrections):
            corrections.append("documented-test-repair")
            return original_parser(html)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "source.parquet", root / "output.parquet"
            self.snapshot(source)
            with patch.object(IntermediateParser, "parse_letter_html", side_effect=corrected):
                report = rebuild_letters.rebuild(source, output, workers=1)
            self.assertEqual(report["correction_counts"], {"documented-test-repair": 2})
            self.assertEqual(report["corrections_by_letter"], {
                "20": ["documented-test-repair"], "10": ["documented-test-repair"],
            })

    def test_failed_conversion_keeps_previous_export_and_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "source.parquet", root / "output.parquet"
            self.snapshot(source)
            output.write_bytes(b"previous complete export")
            with patch.object(rebuild_letters, "_convert", side_effect=ValueError("broken source")):
                with self.assertRaisesRegex(ValueError, "broken source"):
                    rebuild_letters.rebuild(source, output, workers=1)
            self.assertEqual(output.read_bytes(), b"previous complete export")
            self.assertEqual(list(root.glob(".*.tmp")), [])

    def test_missing_heading_in_markdown_stops_export(self):
        row = {"id": 20, "html": HTML}
        with patch.object(rebuild_letters, "markdownify", return_value="Only a paragraph."):
            with self.assertRaisesRegex(ValueError, "Markdown headings differ"):
                rebuild_letters._convert(row)

    def test_bounded_workers_rebuild_every_row(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "source.parquet", root / "output.parquet"
            self.snapshot(source)
            report = rebuild_letters.rebuild(source, output, workers=2, batch_size=1)
            self.assertEqual(report["rows"], 2)
            self.assertEqual(pq.read_table(output)["id"].to_pylist(), [20, 10])


if __name__ == "__main__":
    unittest.main()
