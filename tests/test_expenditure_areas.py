import unittest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pyarrow.parquet as pq

from services.expenditure_areas import fetch_areas
from scripts import build_letters_parquet as builder


class ExpenditureAreaTests(unittest.IsolatedAsyncioTestCase):
    def test_parquet_uses_integer_lists(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "letters.parquet"
            row = {"id": 1, "html": "h", "xhtml": "x", "md": "m", "expenditure_areas": "5;7"}
            with patch("sys.argv", ["builder", "--output", str(output)]), \
                 patch.object(builder, "_load_metadata", return_value=(["expenditure_areas"], {1: {"expenditure_areas": "5;7"}})), \
                 patch.object(builder, "_letter_ids", return_value=[1]), \
                 patch.object(builder, "_build_rows", return_value=[builder._ordered_row(row, ["expenditure_areas"])]):
                builder.main()
            table = pq.read_table(output)
            self.assertEqual(table["expenditure_areas"].to_pylist(), [[5, 7]])
            self.assertEqual(str(table.schema.field("expenditure_areas").type), "list<element: int16>")

    async def test_list_pages_assign_each_original_and_amendment_to_multiple_areas(self):
        def response(url):
            if url.endswith('/statsliggaren/'):
                content = '<a href="/archive?PeriodId=2003">2003</a>'
            elif '/archive?' in url:
                content = ('<a href="/statsliggaren/regleringsbrev---Listsida-UO/?PeriodId=2003&UOId=5">5</a>'
                           '<a href="/statsliggaren/regleringsbrev---Listsida-UO/?PeriodId=2003&UOId=7">7</a>')
            else:
                content = ('<nav id="Regleringsbrev">'
                           '<a href="/statsliggaren/regleringsbrev/?RBID=1">Regleringsbrev</a>'
                           '<a href="/statsliggaren/regleringsbrev/?RBID=2">Ändringsbeslut</a>'
                           '</nav>')
            return Mock(text=content)

        downloader = Mock(_get_with_retry=AsyncMock(side_effect=response))
        self.assertEqual(await fetch_areas(downloader, {2003}), {1: {5, 7}, 2: {5, 7}})
