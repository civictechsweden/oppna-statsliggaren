import asyncio

import statsliggaren as sl
from services.downloader import Downloader
from services.writer import Writer

SAVE_LETTER_FILES = False


async def main():
    downloader = Downloader()

    try:
        metadata = sl.get_local_metadata()
        attachments = sl.get_local_attachments()

        new_metadata, new_attachments, letters = await sl.init(downloader)
        metadata.extend(new_metadata)
        attachments.extend(new_attachments)

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
    asyncio.run(main())
