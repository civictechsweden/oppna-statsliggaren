import unittest
from unittest.mock import AsyncMock, Mock

from services.expenditure_areas import fetch_areas


class ExpenditureAreaTests(unittest.IsolatedAsyncioTestCase):
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
