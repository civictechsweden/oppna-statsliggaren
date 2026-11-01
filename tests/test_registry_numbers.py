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

    def test_legacy_letterhead_expands_grouped_shorthand(self):
        letter = (
            '<table class="universe_tbl"><tr><td class="dnr">'
            '<span class="diarie">Jo2002/673, 3076 (delvis)<br>'
            'Jo1997/934<br>Se bilaga 1</span></td></tr></table>'
        )
        self.assertEqual(
            Parser.extract_registry_numbers(letter),
            ['Jo2002/673', 'Jo2002/3076 (delvis)', 'Jo1997/934'],
        )

    def test_grouped_numbers_share_the_trailing_unit_code(self):
        self.assertEqual(
            Parser._split_registry_numbers('U2003/421,4605/IS'),
            ['U2003/421/IS', 'U2003/4605/IS'],
        )
        self.assertEqual(
            Parser._split_registry_numbers(
                'Ku2010/1203, 2011/14, 437/KV, 1960/RFS (delvis)'
            ),
            [
                'Ku2010/1203', 'Ku2011/14/KV',
                'Ku2011/437/KV', 'Ku2011/1960/RFS (delvis)',
            ],
        )

    def test_comma_before_delvis_and_2002_unit_exception(self):
        self.assertEqual(
            Parser._split_registry_numbers('Jo2007/2502, delvis'),
            ['Jo2007/2502 (delvis)'],
        )
        self.assertEqual(
            Parser._split_registry_numbers('N2005/9907/BS, (delvis)'),
            ['N2005/9907/BS (delvis)'],
        )
        self.assertEqual(
            Parser._split_registry_numbers('U2002/4719/V,F'),
            ['U2002/4719/V', 'U2002/4719/F'],
        )

    def test_comma_groups_continued_across_letterhead_lines(self):
        letter = (
            '<div id="BrevHuvud"><div id="DiarieNr">'
            'Ku2010/1055,1056,<br>1658,1688/KV<br>'
            '</div></div>'
        )
        self.assertEqual(
            Parser.extract_registry_numbers(letter),
            [
                'Ku2010/1055/KV', 'Ku2010/1056/KV',
                'Ku2010/1658/KV', 'Ku2010/1688/KV',
            ],
        )

    def test_complete_numbers_separated_by_spaces_and_misplaced_slash(self):
        self.assertEqual(
            Parser._split_registry_numbers(
                'U2009/2227,2314/UH U2009/1682/SAM (delvis)'
            ),
            ['U2009/2227/UH', 'U2009/2314/UH', 'U2009/1682/SAM (delvis)'],
        )
        self.assertEqual(
            Parser._split_registry_numbers('Ku2012/740/1341/KO Ku2013/506,560/KO'),
            [
                'Ku2012/740/KO', 'Ku2012/1341/KO',
                'Ku2013/506/KO', 'Ku2013/560/KO',
            ],
        )
        self.assertEqual(
            Parser._split_registry_numbers('2008/4489,5656,6758,7290/UH'),
            [
                'U2008/4489/UH', 'U2008/5656/UH',
                'U2008/6758/UH', 'U2008/7290/UH',
            ],
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
            'UD2026/15651;UD2025/04042 (delvis);'
            'Jo2002/673;Jo2002/3076 (delvis)',
        )

    def test_parquet_list_type(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = [
                'UD2026/15651', 'UD2025/04042 (delvis)',
                'Jo2002/673', 'Jo2002/3076 (delvis)',
            ]
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
