import asyncio

import httpx

DOMAIN = "https://www.statskontoret.se"
URL = DOMAIN + "/statsliggaren/regleringsbrev/?RBID={}"
SEARCH_URL = (
    DOMAIN + "/statsliggaren/sok-regleringsbrev/Search?sortOrder=Publiceringsdatum"
)


class Downloader(object):
    def __init__(self):
        transport = httpx.AsyncHTTPTransport(retries=3)
        self.s = httpx.AsyncClient(transport=transport, timeout=10)

    async def _get_with_retry(self, url, retries=3) -> httpx.Response:
        for i in range(retries):
            try:
                return await self.s.get(url)
            except httpx.TimeoutException:
                print(f"Timeout fetching {url}, retrying ({i + 1}/{retries})...")
                if i == retries - 1:
                    raise
                await asyncio.sleep(1)

        raise RuntimeError(f"Failed to fetch {url} after {retries} retries")

    async def fetch_search(self):
        print("Fetching the search page...")
        return await self._get_with_retry(SEARCH_URL)

    async def fetch_page(self, rbid: int) -> httpx.Response:
        print(f"Fetching info for RBID {rbid}...")
        return await self._get_with_retry(URL.format(rbid))

    async def aclose(self):
        await self.s.aclose()
