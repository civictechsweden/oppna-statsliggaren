import asyncio
import httpx

URL = "https://www.statskontoret.se/statsliggaren/regleringsbrev/?RBID={}"
SEARCH_URL = "https://www.statskontoret.se/statsliggaren/sok-regleringsbrev/Search?sortOrder=Publiceringsdatum"


class Downloader(object):
    def __init__(self):
        self.s = httpx.AsyncClient(timeout=30)

    async def fetch_search(self):
        print("Fetching the search page...")
        return await self.s.get(SEARCH_URL)

    async def fetch_page(self, rbid: int):
        print(f"Fetching info for RBID {rbid}...")
        response = await self.s.get(URL.format(rbid))
        response.id = rbid
        return response

    async def fetch_pages(self, rbids: list[int]):
        tasks = [self.fetch_page(rbid) for rbid in rbids]
        responses = []
        for f in asyncio.as_completed(tasks):
            response = await f
            responses.append(response)
            print(f"Fetched info for RBID {response.id} ({len(responses)}/{len(rbids)})")

        return responses
