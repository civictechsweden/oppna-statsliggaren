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


def get_latest_remote_rbid(downloader=Downloader()) -> int:
    return Parser.parse_latest_remote_rbid(downloader.fetch_search())


def get_rbids_to_fetch(downloader=Downloader()) -> list[int]:
    local_rbids = get_local_rbids()
    latest_remote_rbid = get_latest_remote_rbid(downloader)

    if local_rbids:
        latest_local_rbid = local_rbids[-1]
        missing_local_rbids = get_missing_local_rbids(local_rbids)
        return missing_local_rbids[-300:] + [
            i for i in range(latest_local_rbid + 1, latest_remote_rbid + 1)
        ]
    else:
        return [i for i in range(0, latest_remote_rbid + 1)]


def get_metadata(page: int, downloader=Downloader()):
    return Parser.parse_metadata(downloader.fetch_page(page))


def get_metadatas(pages: list[int], downloader=Downloader()):
    return Parser.parse_metadatas(downloader.fetch_pages(pages))
