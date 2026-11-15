"""Refresh the organisation registry and annotate the complete letter catalogue.

uv run -m scripts.build_organisations [--parquet letters.parquet]

Acquisition uses the public annual agency indexes, supplemented by reviewed
collective membership in data/collective_organisations.json. No letter bodies or
binary files are downloaded. The optional Parquet update changes metadata only.
"""

import argparse
import asyncio
import csv
import json
from pathlib import Path
import tempfile

import pyarrow as pa
import pyarrow.parquet as pq
from dotenv import load_dotenv

from services.downloader import Downloader
from services.organisations import (
    ROOT,
    REGISTRY_PATH,
    acquire_registry,
    assign_organisation_ids,
    finish_registry,
    load_registry,
    validate_registry,
)
from services.writer import Writer


def update_parquet(path, rows):
    """Stream a metadata-only update; verify all previous columns are unchanged."""
    ids = {
        int(row["rbid"]): [
            int(value) for value in row["organisation_ids"].split(";") if value
        ]
        for row in rows
    }
    with pq.ParquetFile(path) as original:
        fields = [
            field for field in original.schema_arrow if field.name != "organisation_ids"
        ]
        schema = pa.schema(
            [*fields, pa.field("organisation_ids", pa.list_(pa.int32()))],
            metadata=original.schema_arrow.metadata,
        )
        with tempfile.NamedTemporaryFile(
            dir=path.parent, suffix=".parquet.tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
        seen = set()
        try:
            with pq.ParquetWriter(
                temporary, schema, compression="zstd", use_dictionary=False
            ) as writer:
                for batch in original.iter_batches(batch_size=128):
                    table = pa.Table.from_batches([batch]).select(
                        [field.name for field in fields]
                    )
                    row_ids = table["id"].to_pylist()
                    updated = table.append_column(
                        "organisation_ids",
                        pa.array(
                            [ids[key] for key in row_ids], type=pa.list_(pa.int32())
                        ),
                    )
                    if not updated.select(table.column_names).equals(table):
                        raise ValueError("Organisation backfill changed original data")
                    writer.write_table(updated)
                    seen.update(row_ids)
            if seen != ids.keys():
                raise ValueError("Parquet and CSV letter IDs differ")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


async def main(parquet=None):
    load_dotenv(ROOT / ".env")
    with (ROOT / "letters.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    downloader = Downloader()
    try:
        registry = await acquire_registry(
            downloader,
            {int(row["year"]) for row in rows},
            load_registry() if REGISTRY_PATH.exists() else None,
        )
    finally:
        await downloader.aclose()
    assign_organisation_ids(rows, registry)
    finish_registry(registry)
    validate_registry(registry)
    if parquet is not None:
        update_parquet(parquet, rows)
    Writer.write_csv(rows, str(ROOT / "letters.csv"))
    REGISTRY_PATH.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Recorded {len(registry['organisations'])} organisations and annotated {len(rows)} letters"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parquet", type=Path)
    args = parser.parse_args()
    asyncio.run(main(args.parquet))
