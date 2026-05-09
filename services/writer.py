import asyncio
import csv
import json
import os
from concurrent.futures import ProcessPoolExecutor
import mdformat
from markdownify import markdownify as md
from services.cleaner import Cleaner
from services.intermediate_parser import IntermediateParser


def save_letter_sync(rbid, content):
    Writer.write_text(content, f"letters/html/{rbid}.html")
    xhtml_content = IntermediateParser.parse_letter_html(content)
    Writer.write_text(xhtml_content, f"letters/xhtml/{rbid}.xhtml")
    Writer.write_text(
        Cleaner.clean_markdown(
            mdformat.text(
                md(xhtml_content, heading_style="ATX"),
                options={"number": True},
            )
        ),
        f"letters/md/{rbid}.md",
    )


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
        os.makedirs("letters/xhtml", exist_ok=True)
        os.makedirs("letters/md", exist_ok=True)

        print(f"Saving {len(letters)} letters...", flush=True)

        loop = asyncio.get_running_loop()
        # Create a process pool with a reasonable number of workers (defaults to CPU count)
        with ProcessPoolExecutor() as pool:
            semaphore = asyncio.Semaphore(100) # Still limit concurrency to avoid too many queued tasks

            async def save_letter(rbid, content):
                async with semaphore:
                    await loop.run_in_executor(pool, save_letter_sync, rbid, content)

            tasks = []
            for rbid in letters:
                letter = letters[rbid]
                if letter:
                    tasks.append(save_letter(rbid, letter))

            if tasks:
                await asyncio.gather(*tasks)

        print("Done.", flush=True)
