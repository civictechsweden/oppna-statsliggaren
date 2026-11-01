import csv
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq

from scripts.backfill_diary_numbers import backfill
from scripts import build_letters_parquet as builder
from scripts.build_letters_parquet import _metadata_value, _normalize_existing_rows
from services.parser import Parser


class DiaryNumberTests(unittest.TestCase):
    def test_current_letterhead_keeps_multiple_numbers_and_qualifiers(self):
        letter = (
            '<div id="BrevHuvud"><div id="DiarieNr">'
            'Fö2025/01617<br>Fö2026/00496 (delvis)<br>Fö2026/00498<br>'
            '</div></div><p>Body mentions Fi2026/99999</p>'
        )
        self.assertEqual(
            Parser.extract_diary_numbers(letter),
            ['Fö2025/01617', 'Fö2026/00496 (delvis)', 'Fö2026/00498'],
        )

    def test_legacy_letterhead_preserves_grouped_shorthand(self):
        letter = (
            '<table class="universe_tbl"><tr><td class="dnr">'
            '<span class="diarie">Jo2002/673, 3076 (delvis)<br>'
            'Jo1997/934<br>Se bilaga 1</span></td></tr></table>'
        )
        self.assertEqual(
            Parser.extract_diary_numbers(letter),
            ['Jo2002/673, 3076 (delvis)', 'Jo1997/934'],
        )

    def test_legacy_line_break_inside_number(self):
        letter = (
            '<table class="universe_tbl"><tr><td>'
            '<span class="diarie">Ju2002/9142/<br>DOM (delvis)<br>'
            'Fö 2002/<br>1876/EPS</span></td></tr></table>'
        )
        self.assertEqual(
            Parser.extract_diary_numbers(letter),
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
            Parser.extract_diary_numbers(letter), ['U2003/4789/DK (slutligt)']
        )

    def test_blank_letterhead_has_no_diary_numbers(self):
        letter = '<div id="BrevHuvud"><div id="DiarieNr"></div></div>'
        self.assertEqual(Parser.extract_diary_numbers(letter), [])

    def test_metadata_serializes_csv_array(self):
        response = SimpleNamespace(
            status_code=200,
            text=(
                '<title>Regleringsbrev 2026 Myndighet Test - Statskontoret</title>'
                '<section id="letter"><div id="BrevHuvud">'
                '<div id="DiarieNr">UD2026/15651</div>2026-10-15'
                '</div></section>'
            ),
        )
        metadata, _, _ = Parser.parse_metadata(response, 1)
        self.assertEqual(json.loads(metadata['diary_numbers']), ['UD2026/15651'])

    def test_backfill_and_parquet_list_type(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.parquet'
            csv_path = root / 'letters.csv'
            pq.write_table(pa.Table.from_pylist([
                {'id': 1, 'html': '<div id="BrevHuvud"><div id="DiarieNr">UD2026/15651</div></div>'},
                {'id': 2, 'html': '<div id="BrevHuvud"><div id="DiarieNr"></div></div>'},
            ]), source)
            csv_path.write_text('rbid,department,expenditure_areas,pdf\n1,Utrikesdepartementet,7,True\n2,,8,False\n')
            counts = backfill(source, csv_path)
            self.assertEqual(counts, {'one': 1, 'zero': 1})
            with csv_path.open(newline='') as handle:
                reader = csv.DictReader(handle)
                fields = reader.fieldnames
                rows = list(reader)
            self.assertEqual(fields, ['rbid', 'department', 'expenditure_areas', 'diary_numbers', 'pdf'])
            self.assertEqual(_metadata_value('diary_numbers', rows[0]['diary_numbers']), ['UD2026/15651'])
            self.assertEqual(_metadata_value('diary_numbers', rows[1]['diary_numbers']), [])
            normalized, changed = _normalize_existing_rows(
                pa.Table.from_pylist([{'id': 1, 'html': 'original', 'xhtml': 'cleaned', 'md': 'markdown'}]),
                ['diary_numbers'],
                {1: {'diary_numbers': rows[0]['diary_numbers']}},
            )
            self.assertTrue(changed)
            self.assertEqual(normalized[0]['diary_numbers'], ['UD2026/15651'])

            output = root / 'output.parquet'
            pq.write_table(pa.Table.from_pylist([
                {'id': 1, 'html': 'original', 'xhtml': 'cleaned', 'md': 'markdown'},
            ]), output)
            with patch('sys.argv', ['builder', '--output', str(output)]), \
                 patch.object(builder, '_load_metadata', return_value=(
                     ['diary_numbers'], {1: {'diary_numbers': rows[0]['diary_numbers']}}
                 )), \
                 patch.object(builder, '_letter_ids', return_value=[]):
                builder.main()
            table = pq.read_table(output)
            self.assertEqual(table.schema.field('diary_numbers').type, pa.list_(pa.string()))
            self.assertEqual(table['diary_numbers'].to_pylist(), [['UD2026/15651']])
