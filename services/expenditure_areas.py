"""Expenditure areas assigned by Statsliggaren's annual UO lists."""

import asyncio
import re
from datetime import date
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from services.downloader import DOMAIN


async def fetch_areas(downloader, years: set[int]) -> dict[int, set[int]]:
    index = BeautifulSoup((await downloader._get_with_retry(DOMAIN + "/statsliggaren/")).text, "html.parser")
    year_urls = {date.today().year: DOMAIN + "/statsliggaren/"} if date.today().year in years else {}
    for link in index.select("a[href*='PeriodId=']"):
        if link.get_text(strip=True).isdigit():
            year = int(link.get_text(strip=True))
            if year in years:
                year_urls[year] = f"{DOMAIN}/statsliggaren/?PeriodId={year}"
    if years - year_urls.keys():
        raise ValueError(f"Missing Statsliggaren years: {sorted(years - year_urls.keys())}")

    semaphore = asyncio.Semaphore(6)

    async def get(url):
        async with semaphore:
            return (await downloader._get_with_retry(url)).text

    pages = await asyncio.gather(*(get(url) for url in year_urls.values()))
    area_urls = set()
    for page in pages:
        soup = BeautifulSoup(page, "html.parser")
        for link in soup.select("a[href*='Listsida-UO']"):
            url = urljoin(DOMAIN, link["href"])
            params = parse_qs(urlparse(url).query)
            if int(params["PeriodId"][0]) in years:
                area_urls.add(url)
    if not area_urls:
        raise ValueError("No expenditure-area lists found")

    assignments: dict[int, set[int]] = {}
    for url, page in zip(sorted(area_urls), await asyncio.gather(*(get(url) for url in sorted(area_urls)))):
        soup = BeautifulSoup(page, "html.parser")
        nav = soup.select_one("#Regleringsbrev")
        if nav is None:
            raise ValueError(f"Missing letter list at {url}")
        area = int(parse_qs(urlparse(url).query)["UOId"][0])
        for link in nav.select("a[href*='RBID=']"):
            match = re.search(r"[?&]RBID=(\d+)", link["href"], re.IGNORECASE)
            if match:
                assignments.setdefault(int(match[1]), set()).add(area)
    return assignments
