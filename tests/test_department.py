import unittest
from types import SimpleNamespace

from services.parser import Parser
from scripts.build_letters_parquet import _normalize_existing_rows
import pyarrow as pa


class DepartmentTests(unittest.TestCase):
    def test_letterhead_variants(self):
        for markup in [
            '<div id="BrevHuvud"><div class="avs">{}</div></div>',
            '<div class="section1"><span class="depNamn">{}</span></div>',
            '<div class="documentHead"><span class="depNamn">{}</span></div>',
            '<table><tr><td><span class="departement">{}</span></td></tr></table>',
        ]:
            with self.subTest(markup=markup):
                self.assertEqual(
                    Parser.extract_department(markup.format('Landsbygds- och\n infrastrukturdepartementet<br>')),
                    "Landsbygds- och infrastrukturdepartementet",
                )

    def test_does_not_infer_department_from_body_mentions(self):
        self.assertIsNone(Parser.extract_department('<p>Redovisas till Finansdepartementet.</p>'))
        self.assertIsNone(Parser.extract_department('<div class="avs"> </div>'))

    def test_metadata_for_both_categories(self):
        for category, name in [("Myndighet", "Statskontoret"), ("Anslag", "1:1")]:
            response = SimpleNamespace(status_code=200, text=(
                f'<title>Regleringsbrev 2026 {category} {name} - Statskontoret</title>'
                '<section id="letter"><div id="BrevHuvud">'
                '<div class="avs">Finansdepartementet</div>2025-12-18</div></section>'
            ))
            metadata, _, _ = Parser.parse_metadata(response, 1)
            self.assertEqual(metadata["department"], "Finansdepartementet")
            self.assertEqual(metadata["category"], category)

    def test_parquet_refresh_adds_department_without_changing_content(self):
        table = pa.Table.from_pylist([{"id": 1, "html": "original", "xhtml": "cleaned", "md": "markdown"}])
        rows, changed = _normalize_existing_rows(table, ["department"], {1: {"department": "Finansdepartementet"}})
        self.assertTrue(changed)
        self.assertEqual(rows[0]["department"], "Finansdepartementet")
        self.assertEqual(rows[0]["md"], "markdown")
