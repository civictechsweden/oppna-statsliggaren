import asyncio
import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import HfApi, get_token

import statsliggaren as sl
from services.artifacts import convert_pending_attachments, fetch_source_files
from services.downloader import Downloader
from services.expenditure_areas import fetch_areas
from services.writer import Writer

load_dotenv()

SAVE_LETTER_FILES = True


async def main(refresh_since: str | None = None, scan_all_gaps: bool = False, repo_id: str | None = None):
    downloader = Downloader()

    try:
        metadata = sl.get_local_metadata()
        previous_areas = {int(row["rbid"]): row.get("expenditure_areas", "") for row in metadata}
        attachments = sl.get_local_attachments()

        ids = await sl.get_rbids_to_fetch(downloader, refresh_since, scan_all_gaps)
        new_metadata, new_attachments, letters = await sl.get_metadatas(ids, downloader)
        for row in new_metadata:
            row["expenditure_areas"] = previous_areas.get(row["rbid"], "")
        refreshed = {row["rbid"] for row in new_metadata}
        metadata = [row for row in metadata if int(row["rbid"]) not in refreshed] + new_metadata
        attachments = [row for row in attachments if int(row["rbid"]) not in refreshed] + new_attachments

        years = {
            int(row["year"]) for row in metadata
            if not refresh_since or int(row["year"]) >= int(refresh_since[:4]) - 1
            or int(row["rbid"]) in refreshed
        }
        if years:
            areas = await fetch_areas(downloader, years)
            for row in metadata:
                codes = areas.get(int(row["rbid"]))
                if codes is not None:
                    row["expenditure_areas"] = ";".join(str(code) for code in sorted(codes))

        Writer.write_csv(sorted(metadata, key=lambda d: int(d["rbid"])), "letters.csv")
        Writer.write_csv(
            sorted(attachments, key=lambda d: (int(d["rbid"]), int(d["id"]))),
            "attachments.csv",
        )

        if not SAVE_LETTER_FILES:
            return

        await Writer.save_letters_batch(letters)
    finally:
        await downloader.aclose()

    if repo_id:
        api = HfApi(token=os.getenv("HF_TOKEN") or get_token())
        await fetch_source_files(
            {int(row["rbid"]): row for row in metadata}, attachments,
            set(letters), api, repo_id, Path("letters"),
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-since", help="Refetch existing letters decided on or after YYYY-MM-DD.")
    parser.add_argument("--scan-all-gaps", action="store_true", help="Recheck missing IDs in the refresh period.")
    parser.add_argument("--repo-id", help="Fetch PDFs and attachments for this Hugging Face dataset.")
    parser.add_argument("--convert-attachments", action="store_true", help="Convert fetched legacy attachments.")
    args = parser.parse_args()
    if args.convert_attachments:
        convert_pending_attachments(Path("letters"))
    else:
        if args.refresh_since:
            from datetime import date
            date.fromisoformat(args.refresh_since)
        asyncio.run(main(args.refresh_since, args.scan_all_gaps, args.repo_id))
