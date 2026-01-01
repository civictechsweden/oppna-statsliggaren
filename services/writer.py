import asyncio
import csv
import json
import os
from markdownify import markdownify as md


class Writer(object):
    @staticmethod
    def write_json(dict: dict | list, filename: str):
        with open(filename, "w") as fp:
            json_string = json.dumps(dict, ensure_ascii=False, indent=4).encode("utf-8")
            fp.write(json_string.decode())

    @staticmethod
    def write_csv(dict: list, filename: str):
        if not len(dict):
            return

        keys = dict[0].keys()

        with open(filename, "w", newline="") as output_file:
            dict_writer = csv.DictWriter(output_file, keys)
            dict_writer.writeheader()
            dict_writer.writerows(dict)

    @staticmethod
    def write_text(text: str, filename: str):
        with open(filename, "w") as fp:
            fp.write(text)

    @staticmethod
    async def save_letters_batch(letters: dict):
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
