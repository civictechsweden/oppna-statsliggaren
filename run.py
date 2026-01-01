import asyncio
import os
import sys

import statsliggaren as sl
from services.writer import Writer
from markdownify import markdownify as md

SAVE_LETTER_FILES = False

async def main():
    if await sl.get_latest_remote_rbid() in sl.get_local_rbids():
        print("No new regleringsbrev to fetch.")
        sys.exit()

    metadata = sl.get_local_metadata()
    attachments = sl.get_local_attachments()

    new_metadata, new_attachments, letters = await sl.init()
    metadata.extend(new_metadata)
    attachments.extend(new_attachments)

    Writer.write_csv(sorted(metadata, key=lambda d: int(d["rbid"])), "letters.csv")
    Writer.write_csv(sorted(attachments, key=lambda d: int(d["rbid"])), "attachments.csv")

    if not SAVE_LETTER_FILES:
        sys.exit()

    os.makedirs("letters/html", exist_ok=True)
    os.makedirs("letters/md", exist_ok=True)

    print(f"Saving {len(letters)} letters...", flush=True)

    semaphore = asyncio.Semaphore(100)

    def save_letter_sync(rbid, content):
        Writer.write_text(content, f"letters/html/{rbid}.html")
        Writer.write_text(md(content), f"letters/md/{rbid}.md")

    async def save_letter(rbid, content):
        async with semaphore:
            await asyncio.to_thread(save_letter_sync, rbid, content)

    tasks = []
    for rbid in letters:
        letter = letters[rbid]
        if letter:
            tasks.append(save_letter(rbid, letter))

    if tasks:
        await asyncio.gather(*tasks)
    
    print("Done.", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
