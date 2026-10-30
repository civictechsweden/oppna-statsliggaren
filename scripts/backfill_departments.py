"""Backfill letterhead departments from a saved export, fetching uncached letters."""

import argparse
import asyncio
import csv
from pathlib import Path

import pyarrow.parquet as pq

from services.downloader import Downloader
from services.parser import Parser


async def backfill(parquet: Path, csv_path: Path) -> None:
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    if "department" not in fields:
        fields.insert(fields.index("pdf"), "department")

    by_id = {int(row["rbid"]): row for row in rows}
    for batch in pq.ParquetFile(parquet).iter_batches(columns=["id", "html"], batch_size=128):
        for item in batch.to_pylist():
            row = by_id.get(int(item["id"]))
            if row is not None and not row.get("department"):
                row["department"] = Parser.extract_department(item["html"])
        print(f"Departments filled: {sum(bool(row.get('department')) for row in rows)}/{len(rows)}", flush=True)

    missing = [row for row in rows if not row.get("department")]
    downloader = Downloader()
    semaphore = asyncio.Semaphore(4)

    async def fetch(row):
        async with semaphore:
            response = await downloader.fetch_page(int(row["rbid"]))
            response.raise_for_status()
            letter = Parser._extract_letter(response.text)
            row["department"] = Parser.extract_department(letter) if letter else None

    try:
        await asyncio.gather(*(fetch(row) for row in missing))
    finally:
        await downloader.aclose()

    missing_ids = [row["rbid"] for row in rows if not row.get("department")]
    if missing_ids:
        raise RuntimeError(f"Departments missing for {missing_ids}; CSV not written")
    temporary = csv_path.with_suffix(".csv.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(csv_path)
    print(f"Updated {len(rows)} departments in {csv_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parquet", type=Path, required=True)
    parser.add_argument("--csv", type=Path, default=Path("letters.csv"))
    args = parser.parse_args()
    asyncio.run(backfill(args.parquet, args.csv))
