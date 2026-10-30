"""Add annual UO list memberships to the existing letter catalogue."""

import asyncio

from services.downloader import Downloader
from services.expenditure_areas import fetch_areas
from services.writer import Writer
import statsliggaren as sl


async def main():
    rows = sl.get_local_metadata()
    years = {int(row["year"]) for row in rows}
    downloader = Downloader()
    try:
        assignments = await fetch_areas(downloader, years)
    finally:
        await downloader.aclose()
    for row in rows:
        row["expenditure_areas"] = ";".join(str(code) for code in sorted(assignments.get(int(row["rbid"]), set())))
    Writer.write_csv(rows, "letters.csv")
    print(f"Updated {len(rows)} letters across {len(years)} years")


if __name__ == "__main__":
    asyncio.run(main())
