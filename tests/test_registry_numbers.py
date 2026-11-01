import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq

from scripts import build_letters_parquet as builder
from scripts.build_letters_parquet import _metadata_value, _normalize_existing_rows
from services.parser import Parser


class RegistryNumberTests(unittest.TestCase):
    def test_current_letterhead_keeps_multiple_numbers_and_qualifiers(self):
        letter = (
            '<div id="BrevHuvud"><div id="DiarieNr">'
            'Fö2025/01617<br>Fö2026/00496 (delvis)<br>Fö2026/00498<br>'
            '</div></div><p>Body mentions Fi2026/99999</p>'
        )
        self.assertEqual(
            Parser.extract_registry_numbers(letter),
            ['Fö2025/01617', 'Fö2026/00496 (delvis)', 'Fö2026/00498'],
        )

    def test_legacy_letterhead_preserves_grouped_shorthand(self):
        letter = (
            '<table class="universe_tbl"><tr><td class="dnr">'
            '<span class="diarie">Jo2002/673, 3076 (delvis)<br>'
            'Jo1997/934<br>Se bilaga 1</span></td></tr></table>'
        )
        self.assertEqual(
            Parser.extract_registry_numbers(letter),
            ['Jo2002/673, 3076 (delvis)', 'Jo1997/934'],
        )

    def test_legacy_line_break_inside_number(self):
        letter = (
            '<table class="universe_tbl"><tr><td>'
            '<span class="diarie">Ju2002/9142/<br>DOM (delvis)<br>'
            'Fö 2002/<br>1876/EPS</span></td></tr></table>'
        )
        self.assertEqual(
            Parser.extract_registry_numbers(letter),
            ['Ju2002/9142/DOM (delvis)', 'Fö 2002/1876/EPS'],
        )

    def test_word_letterhead_reads_right_column_and_joins_qualifier(self):
        letter = (
            '<div class="documentHead"><table><tr><td>Fi2025/99999</td>'
            '<td style="width:3.0cm"><table><tr><td>Other</td></tr>'
            '<tr><td>U2003/4789/DK<br>(slutligt)<br></td></tr></table>'
            '</td></tr></table></div>'
        )
        self.assertEqual(
            Parser.extract_registry_numbers(letter), ['U2003/4789/DK (slutligt)']
        )

    def test_blank_letterhead_has_no_registry_numbers(self):
        letter = '<div id="BrevHuvud"><div id="DiarieNr"></div></div>'
        self.assertEqual(Parser.extract_registry_numbers(letter), [])

    def test_unusual_letterhead_number_is_preserved(self):
        letter = (
            '<div id="BrevHuvud"><div id="DiarieNr">'
            'UD2020:18600 (delvis)<br>Se bilaga 1</div></div>'
        )
        self.assertEqual(
            Parser.extract_registry_numbers(letter), ['UD2020:18600 (delvis)']
        )

    def test_metadata_serializes_csv_values(self):
        response = SimpleNamespace(
            status_code=200,
            text=(
                '<title>Regleringsbrev 2026 Myndighet Test - Statskontoret</title>'
                '<section id="letter"><div id="BrevHuvud">'
                '<div id="DiarieNr">UD2026/15651<br>UD2025/04042 (delvis)<br>'
                'Jo2002/673, 3076 (delvis)</div>2026-10-15'
                '</div></section>'
            ),
        )
        metadata, _, _ = Parser.parse_metadata(response, 1)
        self.assertEqual(
            metadata['registry_numbers'],
            'UD2026/15651;UD2025/04042 (delvis);Jo2002/673, 3076 (delvis)',
        )

    def test_parquet_list_type(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = ['UD2026/15651', 'UD2025/04042 (delvis)', 'Jo2002/673, 3076 (delvis)']
            csv_value = ';'.join(expected)
            self.assertEqual(_metadata_value('registry_numbers', csv_value), expected)
            self.assertEqual(_metadata_value('registry_numbers', ''), [])
            normalized, changed = _normalize_existing_rows(
                pa.Table.from_pylist([{'id': 1, 'html': 'original', 'xhtml': 'cleaned', 'md': 'markdown'}]),
                ['registry_numbers'],
                {1: {'registry_numbers': csv_value}},
            )
            self.assertTrue(changed)
            self.assertEqual(normalized[0]['registry_numbers'], expected)

            output = root / 'output.parquet'
            pq.write_table(pa.Table.from_pylist([
                {'id': 1, 'html': 'original', 'xhtml': 'cleaned', 'md': 'markdown'},
            ]), output)
            with patch('sys.argv', ['builder', '--output', str(output)]), \
                 patch.object(builder, '_load_metadata', return_value=(
                     ['registry_numbers'], {1: {'registry_numbers': csv_value}}
                 )), \
                 patch.object(builder, '_letter_ids', return_value=[]):
                builder.main()
            table = pq.read_table(output)
            self.assertEqual(table.schema.field('registry_numbers').type, pa.list_(pa.string()))
            self.assertEqual(table['registry_numbers'].to_pylist(), [expected])
