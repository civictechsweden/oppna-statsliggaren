"""Fetch current PDFs and attachments before dataset publication."""

import argparse
import asyncio
import csv
import json
import os

from huggingface_hub import HfApi, RepoFile, get_token

from scripts.build_letters_parquet import ROOT, LETTERS_DIR, _letter_ids, _load_metadata
from services.artifacts import converted_path, download_files, file_specs, files_to_publish


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-id", required=True)
    args = parser.parse_args()

    api = HfApi(token=os.getenv("HF_TOKEN") or get_token())
    api.create_repo(repo_id=args.repo_id, repo_type="dataset", exist_ok=True)
    remote_files = {
        item.path: item for item in api.list_repo_tree(
            repo_id=args.repo_id, repo_type="dataset", recursive=True
        ) if isinstance(item, RepoFile)
    }
    with (ROOT / "attachments.csv").open(encoding="utf-8", newline="") as handle:
        attachments = list(csv.DictReader(handle))
    _, metadata = _load_metadata()
    specs = file_specs(metadata, attachments, set(_letter_ids()))
    reusable_paths = {
        path for path in remote_files
        if not converted_path(path) or converted_path(path) in remote_files
    }
    downloaded = asyncio.run(download_files(specs, LETTERS_DIR, reusable_paths))
    changed, conversions = files_to_publish(downloaded, LETTERS_DIR, remote_files)
    (LETTERS_DIR / "source_files.json").write_text(json.dumps({
        "paths": changed,
        "conversions": conversions,
    }, indent=2))
    print(f"Fetched {len(downloaded)} files; {len(changed)} changed, {len(conversions)} need conversion")


if __name__ == "__main__":
    main()
