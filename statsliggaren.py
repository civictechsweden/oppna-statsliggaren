from services.downloader import Downloader
from services.parser import Parser


def get_metadata(page, downloader=Downloader()):
    return Parser.parse_metadata(downloader.fetch_page(page))


def get_metadatas(pages, downloader=Downloader()):
    return Parser.parse_metadatas(downloader.fetch_pages(pages))
