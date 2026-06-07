from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterable

import pyarrow as pa
import pyarrow.parquet as pq
from huggingface_hub import HfApi, hf_hub_download
from huggingface_hub.errors import EntryNotFoundError, RepositoryNotFoundError


ROOT = Path(__file__).resolve().parents[1]
LETTERS_DIR = ROOT / "letters"
HTML_DIR = LETTERS_DIR / "html"
XHTML_DIR = LETTERS_DIR / "xhtml"
MD_DIR = LETTERS_DIR / "md"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _letter_ids() -> list[int]:
    return sorted(int(path.stem) for path in HTML_DIR.glob("*.html"))


def _load_row(letter_id: int) -> dict[str, object]:
    html_path = HTML_DIR / f"{letter_id}.html"
    xhtml_path = XHTML_DIR / f"{letter_id}.xhtml"
    md_path = MD_DIR / f"{letter_id}.md"

    if not xhtml_path.exists():
        raise FileNotFoundError(f"missing XHTML for {letter_id}: {xhtml_path}")
    if not md_path.exists():
        raise FileNotFoundError(f"missing Markdown for {letter_id}: {md_path}")

    return {
        "id": letter_id,
        "html": _read_text(html_path),
        "xhtml": _read_text(xhtml_path),
        "md": _read_text(md_path),
    }


def _build_rows(letter_ids: Iterable[int]) -> list[dict[str, object]]:
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(_load_row, letter_ids))


def _existing_ids(parquet_path: Path) -> set[int]:
    if not parquet_path.exists():
        return set()

    table = pq.read_table(parquet_path, columns=["id"])
    return {int(value) for value in table.column("id").to_pylist()}


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
    api.upload_file(
        path_or_fileobj=str(parquet_path),
        path_in_repo=repo_path,
        repo_id=repo_id,
        repo_type="dataset",
        commit_message="Update letters parquet",
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
            local_dir_use_symlinks=False,
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
        help="Hugging Face dataset repo id, for example org/dataset-name.",
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
    args = parser.parse_args()

    parquet_path: Path = args.output

    import os

    token = args.hf_token if args.hf_token is not None else os.getenv("HF_TOKEN")
    repo_id = args.repo_id or None

    if not parquet_path.exists() and repo_id:
        downloaded = _download_existing_from_hf(
            parquet_path=parquet_path,
            repo_id=repo_id,
            repo_path=args.repo_path,
            token=token,
        )
        if downloaded:
            print(f"downloaded existing parquet from {repo_id}/{args.repo_path}")

    source_ids = _letter_ids()
    existing_ids = _existing_ids(parquet_path)
    missing_ids = [letter_id for letter_id in source_ids if letter_id not in existing_ids]

    existing_table = _load_existing_table(parquet_path)

    if missing_ids:
        new_rows = _build_rows(missing_ids)
        new_table = pa.Table.from_pylist(new_rows)
        final_table = (
            pa.concat_tables([existing_table, new_table]) if existing_table else new_table
        )
        final_table = final_table.sort_by([("id", "ascending")])
        _write_table(final_table, parquet_path)
        print(f"updated {parquet_path} with {len(missing_ids)} new rows")
    elif not parquet_path.exists():
        rows = _build_rows(source_ids)
        final_table = pa.Table.from_pylist(rows).sort_by([("id", "ascending")])
        _write_table(final_table, parquet_path)
        print(f"created {parquet_path} with {len(source_ids)} rows")
    else:
        print(
            f"{parquet_path} already contains all {len(source_ids)} locally available rows"
        )

    if repo_id:
        if not token:
            raise RuntimeError("HF upload requested but no HF token was provided")

        _upload_to_hf(parquet_path, repo_id, args.repo_path, token)
        print(f"uploaded {parquet_path} to {repo_id}/{args.repo_path}")


if __name__ == "__main__":
    main()
