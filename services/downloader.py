import asyncio
import os

import httpx
from httpx_ip_rotator import AsyncApiGatewayTransport

DOMAIN = "https://www.statskontoret.se"
URL = DOMAIN + "/statsliggaren/regleringsbrev/?RBID={}"
SEARCH_URL = (
    DOMAIN + "/statsliggaren/sok-regleringsbrev/Search?sortOrder=Publiceringsdatum"
)


class Downloader(object):
    def __init__(self):
        self.gateway_transport = None

        if os.getenv("USE_IP_ROTATOR", False):
            self.gateway_transport = AsyncApiGatewayTransport(
                DOMAIN,
                regions=["eu-north-1"],
                retries=3,
            )
            self.gateway_transport.start()
            self.s = httpx.AsyncClient(
                mounts={DOMAIN: self.gateway_transport},
                timeout=15,
            )
        else:
            transport = httpx.AsyncHTTPTransport(retries=3)
            self.s = httpx.AsyncClient(transport=transport, timeout=10)

    async def _get_with_retry(self, url, retries=3):
        for i in range(retries):
            try:
                return await self.s.get(url)
            except httpx.ReadTimeout:
                print(f"Timeout fetching {url}, retrying ({i + 1}/{retries})...")
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

    async def aclose(self):
        await self.s.aclose()
        if self.gateway_transport is not None:
            self.gateway_transport.shutdown()
