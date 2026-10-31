from __future__ import annotations

import argparse
import asyncio
import csv
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterable

import pyarrow as pa
import pyarrow.parquet as pq
from dotenv import load_dotenv
from huggingface_hub import HfApi, get_token, hf_hub_download

from services.artifacts import convert_attachments, converted_path, download_files, file_specs
from services.downloader import Downloader
from services.writer import Writer, save_letter_sync
from statsliggaren import get_metadatas
from huggingface_hub.errors import EntryNotFoundError, RepositoryNotFoundError


ROOT = Path(__file__).resolve().parents[1]
LETTERS_DIR = ROOT / "letters"
HTML_DIR = LETTERS_DIR / "html"
XHTML_DIR = LETTERS_DIR / "xhtml"
MD_DIR = LETTERS_DIR / "md"
METADATA_CSV = ROOT / "letters.csv"

load_dotenv(ROOT / ".env")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_metadata() -> tuple[list[str], dict[int, dict[str, str]]]:
    with open(METADATA_CSV, encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise RuntimeError(f"{METADATA_CSV} has no header")

        metadata_fields = [field for field in reader.fieldnames if field != "rbid"]
        metadata_by_id = {}
        for row in reader:
            metadata_by_id[int(row["rbid"])] = {
                field: (row.get(field) or "") for field in metadata_fields
            }

    return metadata_fields, metadata_by_id


def _letter_ids() -> list[int]:
    return sorted(int(path.stem) for path in HTML_DIR.glob("*.html"))


def _load_row(
    letter_id: int,
    metadata_fields: list[str],
    metadata_by_id: dict[int, dict[str, str]],
) -> dict[str, object]:
    html_path = HTML_DIR / f"{letter_id}.html"
    xhtml_path = XHTML_DIR / f"{letter_id}.xhtml"
    md_path = MD_DIR / f"{letter_id}.md"

    if not xhtml_path.exists() or not md_path.exists():
        save_letter_sync(letter_id, _read_text(html_path))
    if letter_id not in metadata_by_id:
        raise KeyError(f"missing metadata row for {letter_id} in {METADATA_CSV}")

    row = {
        "id": letter_id,
        "html": _read_text(html_path),
        "xhtml": _read_text(xhtml_path),
        "md": _read_text(md_path),
    }
    row.update(metadata_by_id[letter_id])
    return _ordered_row(row, metadata_fields)


def _build_rows(
    letter_ids: Iterable[int],
    metadata_fields: list[str],
    metadata_by_id: dict[int, dict[str, str]],
) -> list[dict[str, object]]:
    letter_ids = list(letter_ids)
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(
            pool.map(
                _load_row,
                letter_ids,
                [metadata_fields] * len(letter_ids),
                [metadata_by_id] * len(letter_ids),
            )
        )


def _expected_columns(metadata_fields: list[str]) -> list[str]:
    return ["id", *(field for field in metadata_fields if field != "pdf"),
            "html", "xhtml", "md", *(["pdf"] if "pdf" in metadata_fields else [])]


def _metadata_value(field: str, value: object) -> str | list[int]:
    if field == "expenditure_areas":
        if isinstance(value, list):
            return value
        return [int(code) for code in str(value or "").split(";") if code]
    return str(value or "")


def _ordered_row(row: dict[str, object], metadata_fields: list[str]) -> dict[str, object]:
    ordered = {"id": int(row["id"])}
    for field in metadata_fields:
        ordered[field] = _metadata_value(field, row.get(field, ""))
    ordered["html"] = str(row["html"])
    ordered["xhtml"] = str(row["xhtml"])
    ordered["md"] = str(row["md"])
    if "pdf" in ordered:
        ordered["pdf"] = ordered.pop("pdf")
    return ordered


def _normalize_existing_rows(
    existing_table: pa.Table | None,
    metadata_fields: list[str],
    metadata_by_id: dict[int, dict[str, str]],
) -> tuple[list[dict[str, object]], bool]:
    if existing_table is None:
        return [], False

    expected_columns = _expected_columns(metadata_fields)
    rows_need_rewrite = existing_table.schema.names != expected_columns
    normalized_rows = []

    for row in existing_table.to_pylist():
        letter_id = int(row["id"])
        metadata = metadata_by_id.get(letter_id)
        if metadata is None:
            raise KeyError(f"missing metadata row for {letter_id} in {METADATA_CSV}")

        normalized = dict(row)
        for field in metadata_fields:
            value = _metadata_value(field, metadata[field])
            if normalized.get(field, "") != value:
                rows_need_rewrite = True
            normalized[field] = value

        normalized_rows.append(_ordered_row(normalized, metadata_fields))

    return normalized_rows, rows_need_rewrite


def _load_existing_table(parquet_path: Path) -> pa.Table | None:
    if not parquet_path.exists():
        return None
    return pq.read_table(parquet_path)


def _write_table(table: pa.Table, parquet_path: Path) -> None:
    pq.write_table(
        table,
        parquet_path,
        compression="zstd",
        row_group_size=1024,
        use_dictionary=False,
    )


def _upload_to_hf(
    parquet_path: Path,
    repo_id: str,
    repo_path: str,
    token: str | None,
) -> None:
    api = HfApi(token=token)
    api.create_repo(repo_id=repo_id, repo_type="dataset", exist_ok=True)
    with (ROOT / "attachments.csv").open(encoding="utf-8", newline="") as handle:
        attachments = list(csv.DictReader(handle))
    _, metadata = _load_metadata()
    existing_paths = set(api.list_repo_files(repo_id=repo_id, repo_type="dataset"))
    specs = file_specs(metadata, attachments, set(_letter_ids()))
    # A published original may still need a newly introduced OOXML derivative.
    reusable_paths = {path for path in existing_paths
                      if not converted_path(path) or converted_path(path) in existing_paths}
    paths = asyncio.run(download_files(
        specs, LETTERS_DIR, reusable_paths
    ))
    paths.extend(convert_attachments(LETTERS_DIR, paths))
    files = {path: LETTERS_DIR / path for path in paths}
    files.update({
        repo_path: parquet_path,
        "letters.csv": METADATA_CSV,
        "attachments.csv": ROOT / "attachments.csv",
        "README.md": ROOT / "dataset_card.md",
        "unavailable_files.json": LETTERS_DIR / "unavailable_files.json",
    })
    with tempfile.TemporaryDirectory(prefix="hf-publication-", dir=LETTERS_DIR) as temporary:
        staging = Path(temporary)
        for path, source in files.items():
            target = staging / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.hardlink_to(source)
        api.upload_folder(
            repo_id=repo_id,
            repo_type="dataset",
            folder_path=staging,
            commit_message="Refresh letters and attachments",
        )


def _download_existing_from_hf(
    parquet_path: Path,
    repo_id: str,
    repo_path: str,
    token: str | None,
) -> bool:
    parquet_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        downloaded = hf_hub_download(
            repo_id=repo_id,
            filename=repo_path,
            repo_type="dataset",
            token=token,
            local_dir=str(parquet_path.parent),
        )
    except (EntryNotFoundError, RepositoryNotFoundError):
        return False

    downloaded_path = Path(downloaded)
    if downloaded_path != parquet_path:
        parquet_path.write_bytes(downloaded_path.read_bytes())
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "letters.parquet",
        help="Local parquet file to build.",
    )
    parser.add_argument(
        "--repo-id",
        default=None,
        help="Hugging Face dataset repo id. If omitted, HF_DATASET_REPO_ID from the environment is used when --upload is set.",
    )
    parser.add_argument(
        "--repo-path",
        default="letters.parquet",
        help="Path inside the Hugging Face dataset repo.",
    )
    parser.add_argument(
        "--hf-token",
        default=None,
        help="Hugging Face token. Defaults to HF_TOKEN from the environment.",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Upload the resulting parquet file to Hugging Face.",
    )
    args = parser.parse_args()

    parquet_path: Path = args.output
    metadata_fields, metadata_by_id = _load_metadata()

    import os

    token = args.hf_token if args.hf_token is not None else (os.getenv("HF_TOKEN") or get_token())
    repo_id = args.repo_id or None
    if args.upload and repo_id is None:
        repo_id = os.getenv("HF_DATASET_REPO_ID") or None

    if not parquet_path.exists() and args.upload and repo_id:
        downloaded = _download_existing_from_hf(
            parquet_path=parquet_path,
            repo_id=repo_id,
            repo_path=args.repo_path,
            token=token,
        )
        if downloaded:
            print(f"downloaded existing parquet from {repo_id}/{args.repo_path}")

    existing_table = _load_existing_table(parquet_path)
    existing_rows, rows_need_rewrite = _normalize_existing_rows(
        existing_table, metadata_fields, metadata_by_id,
    )
    existing_by_id = {int(row["id"]): row for row in existing_rows}
    missing_ids = sorted(set(metadata_by_id) - set(existing_by_id) - set(_letter_ids()))
    if missing_ids:
        async def fetch_missing():
            downloader = Downloader()
            try:
                _, _, letters = await get_metadatas(missing_ids, downloader)
                if set(letters) != set(missing_ids):
                    raise RuntimeError(f"Missing letter payloads: {sorted(set(missing_ids) - set(letters))}")
                await Writer.save_letters_batch(letters)
            finally:
                await downloader.aclose()
        asyncio.run(fetch_missing())

    source_ids = _letter_ids()
    refreshed_rows = _build_rows(source_ids, metadata_fields, metadata_by_id)
    changed = any(existing_by_id.get(int(row["id"])) != row for row in refreshed_rows)
    existing_by_id.update({int(row["id"]): row for row in refreshed_rows})
    if set(existing_by_id) != set(metadata_by_id):
        raise RuntimeError("Parquet IDs do not match the complete letter catalogue")
    if changed or rows_need_rewrite or not parquet_path.exists():
        table = pa.Table.from_pylist([existing_by_id[key] for key in sorted(existing_by_id)])
        if "expenditure_areas" in metadata_fields:
            index = table.schema.get_field_index("expenditure_areas")
            table = table.set_column(index, "expenditure_areas", pa.array(
                table.column(index).to_pylist(), type=pa.list_(pa.int16())
            ))
        temporary = parquet_path.with_suffix(".parquet.tmp")
        _write_table(table, temporary)
        temporary.replace(parquet_path)
        print(f"updated {parquet_path}: {len(existing_by_id)} letters, {len(source_ids)} local payloads refreshed")
    else:
        print(f"{parquet_path} already contains the current content for {len(existing_by_id)} letters")

    if args.upload:
        if not repo_id:
            raise RuntimeError("HF upload requested but no repo id was provided")
        if not token:
            raise RuntimeError("HF upload requested but no HF token was provided")

        _upload_to_hf(parquet_path, repo_id, args.repo_path, token)
        print(f"uploaded {parquet_path} to {repo_id}/{args.repo_path}")


if __name__ == "__main__":
    main()
