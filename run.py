import asyncio
import argparse

from dotenv import load_dotenv

import statsliggaren as sl
from services.downloader import Downloader
from services.writer import Writer

load_dotenv()

SAVE_LETTER_FILES = True


async def main(refresh_since: str | None = None):
    downloader = Downloader()

    try:
        metadata = sl.get_local_metadata()
        attachments = sl.get_local_attachments()

        ids = await sl.get_rbids_to_fetch(downloader, refresh_since)
        new_metadata, new_attachments, letters = await sl.get_metadatas(ids, downloader)
        refreshed = {row["rbid"] for row in new_metadata}
        metadata = [row for row in metadata if int(row["rbid"]) not in refreshed] + new_metadata
        attachments = [row for row in attachments if int(row["rbid"]) not in refreshed] + new_attachments

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-since", help="Refetch existing letters decided on or after YYYY-MM-DD.")
    args = parser.parse_args()
    if args.refresh_since:
        from datetime import date
        date.fromisoformat(args.refresh_since)
    asyncio.run(main(args.refresh_since))
