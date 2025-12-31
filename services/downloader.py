import httpx

URL = "https://www.statskontoret.se/statsliggaren/regleringsbrev/?RBID={}"
SEARCH_URL = "https://www.statskontoret.se/statsliggaren/sok-regleringsbrev/Search?sortOrder=Publiceringsdatum"


class Downloader(object):
    def __init__(self):
        transport = httpx.AsyncHTTPTransport(retries=3)
        self.s = httpx.AsyncClient(transport=transport, timeout=20)

    async def fetch_search(self):
        print("Fetching the search page...")
        return await self.s.get(SEARCH_URL)

    async def fetch_page(self, rbid: int):
        print(f"Fetching info for RBID {rbid}...")
        response = await self.s.get(URL.format(rbid))
        response.id = rbid
        return response
