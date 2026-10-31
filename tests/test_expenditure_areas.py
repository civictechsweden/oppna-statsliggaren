import unittest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pyarrow.parquet as pq

from services.expenditure_areas import fetch_areas
from scripts import build_letters_parquet as builder
import run


class ExpenditureAreaTests(unittest.IsolatedAsyncioTestCase):
    async def test_refresh_preserves_amendment_area_from_earlier_budget_period(self):
        old = {"rbid": "25279", "date": "2025-01-23", "year": "2025", "expenditure_areas": "22"}
        earlier = {"rbid": "1", "date": "2024-01-01", "year": "2024", "expenditure_areas": "22"}
        refreshed = {"rbid": 25279, "date": "2025-01-23", "year": "2025"}
        downloader = Mock(aclose=AsyncMock())
        with patch.object(run.sl, "get_local_metadata", return_value=[earlier, old]), \
             patch.object(run.sl, "get_local_attachments", return_value=[]), \
             patch.object(run.sl, "get_rbids_to_fetch", new=AsyncMock(return_value=[25279])), \
             patch.object(run.sl, "get_metadatas", new=AsyncMock(return_value=([refreshed], [], {}))), \
             patch.object(run, "fetch_areas", new=AsyncMock(return_value={})) as areas, \
             patch.object(run, "Downloader", return_value=downloader), \
             patch.object(run.Writer, "write_csv") as write_csv, \
             patch.object(run, "SAVE_LETTER_FILES", False):
            await run.main("2025-01-01")
        self.assertEqual(areas.await_args.args[1], {2024, 2025})
        rows = write_csv.call_args_list[0].args[0]
        self.assertEqual(next(row for row in rows if row["rbid"] == 25279)["expenditure_areas"], "22")

    def test_parquet_uses_integer_lists(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "letters.parquet"
            row = {"id": 1, "html": "h", "xhtml": "x", "md": "m", "expenditure_areas": "5;7", "pdf": "True"}
            with patch("sys.argv", ["builder", "--output", str(output)]), \
                 patch.object(builder, "_load_metadata", return_value=(["expenditure_areas", "pdf"], {1: {"expenditure_areas": "5;7", "pdf": "True"}})), \
                 patch.object(builder, "_letter_ids", return_value=[1]), \
                 patch.object(builder, "_build_rows", return_value=[builder._ordered_row(row, ["expenditure_areas", "pdf"])]):
                builder.main()
            table = pq.read_table(output)
            self.assertEqual(table["expenditure_areas"].to_pylist(), [[5, 7]])
            self.assertEqual(str(table.schema.field("expenditure_areas").type), "list<element: int16>")
            self.assertEqual(table.schema.names[-2:], ["md", "pdf"])

    async def test_list_pages_assign_each_original_and_amendment_to_multiple_areas(self):
        def response(url):
            if url.endswith('/statsliggaren/'):
                content = '<a href="/archive?PeriodId=2003">2003</a>'
            elif '/statsliggaren/?PeriodId=2003' in url:
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
        self.assertFalse(any('/link/' in call.args[0] for call in downloader._get_with_retry.await_args_list))
