import httpx
import asyncio

URL = "https://www.statskontoret.se/statsliggaren/regleringsbrev/?RBID={}"
SEARCH_URL = "https://www.statskontoret.se/statsliggaren/sok-regleringsbrev/Search?sortOrder=Publiceringsdatum"


class Downloader(object):
    def __init__(self):
        transport = httpx.AsyncHTTPTransport(retries=3)
        self.s = httpx.AsyncClient(transport=transport, timeout=10)

    async def _get_with_retry(self, url, retries=3):
        for i in range(retries):
            try:
                return await self.s.get(url)
            except httpx.ReadTimeout:
                print(f"Timeout fetching {url}, retrying ({i+1}/{retries})...")
                if i == retries - 1:
                    raise
                await asyncio.sleep(1)

    async def fetch_search(self):
        print("Fetching the search page...")
        return await self._get_with_retry(SEARCH_URL)

    async def fetch_page(self, rbid: int):
        print(f"Fetching info for RBID {rbid}...")
        response = await self._get_with_retry(URL.format(rbid))
        response.id = rbid
        return response
