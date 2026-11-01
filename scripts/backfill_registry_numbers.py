"""Backfill letterhead registry numbers from the raw HTML in letters.parquet."""

import argparse
import csv
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

from services.parser import Parser


def backfill(parquet: Path, csv_path: Path) -> Counter:
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    if "registry_numbers" not in fields:
        fields.insert(fields.index("pdf"), "registry_numbers")

    by_id = {int(row["rbid"]): row for row in rows}
    seen = set()
    counts = Counter()
    for batch in pq.ParquetFile(parquet).iter_batches(
        columns=["id", "html"], batch_size=128
    ):
        for item in batch.to_pylist():
            letter_id = int(item["id"])
            if letter_id not in by_id:
                raise KeyError(f"Parquet letter {letter_id} is missing from {csv_path}")
            numbers = Parser.extract_registry_numbers(item["html"])
            by_id[letter_id]["registry_numbers"] = ";".join(numbers)
            counts["zero" if not numbers else "one" if len(numbers) == 1 else "multiple"] += 1
            seen.add(letter_id)
    if seen != set(by_id):
        raise RuntimeError(f"CSV letters missing from Parquet: {sorted(set(by_id) - seen)[:10]}")

    temporary = csv_path.with_suffix(".csv.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(csv_path)
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parquet", type=Path, required=True)
    parser.add_argument("--csv", type=Path, default=Path("letters.csv"))
    args = parser.parse_args()
    print(backfill(args.parquet, args.csv))
