from concurrent.futures import as_completed
from requests_futures.sessions import FuturesSession

URL = "https://www.esv.se/statsliggaren/regleringsbrev/?RBID={}"


class Downloader(object):

    def __init__(self):
        self.s = FuturesSession(max_workers=30)

    def fetch_page(self, rbid):
        print(f"Fetching info for RBID {rbid}...")

        future = self.s.get(URL.format(rbid))

        future.id = rbid
        return future

    def fetch_pages(self, rbids):
        futures = [self.fetch_page(rbid) for rbid in rbids]

        i = 0
        for future in as_completed(futures):
            i += 1
            print(f"Fetched info for RBID {future.id} ({i}/{len(futures)})")

        return [future for future in futures]
