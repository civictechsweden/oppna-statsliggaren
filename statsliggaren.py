import asyncio
from services.reader import open_csv
from services.downloader import Downloader
from services.parser import Parser


def get_local_metadata() -> list:
    return open_csv("letters.csv")


def get_local_attachments() -> list:
    return open_csv(filename="attachments.csv")


def get_local_rbids() -> list[int]:
    return sorted([int(letter["rbid"]) for letter in get_local_metadata()])


def get_missing_local_rbids(local_rbids: list[int]) -> list[int]:
    all_rbids = range(local_rbids[0], local_rbids[-1])
    return sorted(list(set(all_rbids) - set(local_rbids)))


async def get_latest_remote_rbid(downloader=Downloader()) -> int:
    return Parser.parse_latest_remote_rbid(await downloader.fetch_search())


async def get_rbids_to_fetch(downloader=Downloader()) -> list[int]:
    local_rbids = get_local_rbids()
    latest_remote_rbid = await get_latest_remote_rbid(downloader)

    if local_rbids:
        latest_local_rbid = local_rbids[-1]
        missing_local_rbids = get_missing_local_rbids(local_rbids)
        return missing_local_rbids[-300:] + [
            i for i in range(latest_local_rbid + 1, latest_remote_rbid + 1)
        ]
    else:
        return [i for i in range(0, latest_remote_rbid + 1)]


async def get_metadata(page: int, downloader=Downloader()):
    return Parser.parse_metadata(await downloader.fetch_page(page))


async def get_metadatas(pages: list[int], downloader):
    print(f"Fetching the first 30 RBIDs from the list: {pages[:30]}", flush=True)
    items = []
    all_attachments = []
    letters = {}

    semaphore = asyncio.Semaphore(50)
    loop = asyncio.get_running_loop()

    async def fetch_and_parse(rbid):
        async with semaphore:
            response = await downloader.fetch_page(rbid)
        return await loop.run_in_executor(None, Parser.parse_metadata, response)

    tasks = [fetch_and_parse(rbid) for rbid in pages]

    for i, future in enumerate(asyncio.as_completed(tasks), 1):
        metadata, attachments, letter = await future
        print(f"Processing RBID {metadata['rbid']} ({i}/{len(tasks)})", flush=True)

        if metadata.get("name"):
            items.append(metadata)
            letters[metadata['rbid']] = letter
        all_attachments.extend(attachments)

    return items, all_attachments, letters


async def init():
    downloader = Downloader()
    rbids = await get_rbids_to_fetch(downloader)
    new_metadata, new_attachments, letters = await get_metadatas(rbids, downloader)

    await downloader.s.aclose()

    return new_metadata, new_attachments, letters
