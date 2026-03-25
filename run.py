import asyncio
import sys

from dotenv import load_dotenv

import statsliggaren as sl
from services.downloader import Downloader
from services.writer import Writer

load_dotenv()

SAVE_LETTER_FILES = False


async def main():
    downloader = Downloader()

    try:
        if await sl.get_latest_remote_rbid(downloader) in sl.get_local_rbids():
            print("No new regleringsbrev to fetch.")
            sys.exit()

        metadata = sl.get_local_metadata()
        attachments = sl.get_local_attachments()

        new_metadata, new_attachments, letters = await sl.init(downloader)
        metadata.extend(new_metadata)
        attachments.extend(new_attachments)

        Writer.write_csv(sorted(metadata, key=lambda d: int(d["rbid"])), "letters.csv")
        Writer.write_csv(
            sorted(attachments, key=lambda d: int(d["rbid"])), "attachments.csv"
        )

        if not SAVE_LETTER_FILES:
            sys.exit()

        await Writer.save_letters_batch(letters)
    finally:
        await downloader.aclose()


if __name__ == "__main__":
    asyncio.run(main())
