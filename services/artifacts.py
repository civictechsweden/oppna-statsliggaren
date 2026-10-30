"""Download and publish the original letter PDFs and attachment files."""

import asyncio
from pathlib import Path

from huggingface_hub import CommitOperationAdd

from services.downloader import DOMAIN, Downloader


def file_specs(metadata, attachments, refreshed_ids):
    specs = {}
    for rbid, row in metadata.items():
        if str(row["pdf"]).lower() == "true":
            path = f"pdf/{rbid}.pdf"
            specs[path] = (f"{DOMAIN}/regleringsbrev/{rbid}/pdf?Version=HelaBrevet", rbid in refreshed_ids)
    for row in attachments:
        extension = Path(row["name"]).suffix.lower()
        if not extension or not extension[1:].isalnum():
            raise ValueError(f"Attachment {row['id']} has no usable file extension: {row['name']}")
        path = f"attachments/{int(row['id'])}{extension}"
        refresh = int(row["rbid"]) in refreshed_ids or specs.get(path, (None, False))[1]
        specs[path] = (f"{DOMAIN}/regleringsbrev/bilaga/{int(row['id'])}", refresh)
    return specs


async def download_files(specs, directory: Path, existing_paths: set[str]):
    downloader = Downloader()
    semaphore = asyncio.Semaphore(6)
    paths = []
    unavailable = []

    async def download(path, url, refresh):
        if path in existing_paths and not refresh:
            return
        target = directory / path
        async with semaphore:
            if not target.exists() or refresh:
                response = await downloader._get_with_retry(url)
                if response.status_code == 404:
                    unavailable.append(path)
                    return
                data = response.content
                content_type = response.headers.get("content-type", "").lower()
                if not data or "text/html" in content_type:
                    raise ValueError(f"Expected a document file at {url}, received {content_type}")
                if path.startswith("pdf/") and not data.startswith(b"%PDF"):
                    raise ValueError(f"Expected PDF at {url}")
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_suffix(target.suffix + ".tmp")
                temporary.write_bytes(data)
                temporary.replace(target)
            paths.append(path)
            if len(paths) % 100 == 0:
                print(f"Downloaded {len(paths)} source files", flush=True)

    try:
        await asyncio.gather(*(download(path, *spec) for path, spec in specs.items()))
    finally:
        await downloader.aclose()
    if unavailable:
        print(f"Source returned 404 for {len(unavailable)} files: {sorted(unavailable)}", flush=True)
    return sorted(paths)


def upload_files(api, repo_id: str, directory: Path, paths: list[str]):
    # Small commits allow an interrupted initial archive upload to resume on the
    # next run, without exceeding Hub commit operation limits.
    for offset in range(0, len(paths), 100):
        api.create_commit(
            repo_id=repo_id,
            repo_type="dataset",
            operations=[
                CommitOperationAdd(path_in_repo=path, path_or_fileobj=directory / path)
                for path in paths[offset:offset + 100]
            ],
            commit_message="Refresh letter PDFs and attachments",
        )
        print(f"Published {min(offset + 100, len(paths))}/{len(paths)} source files", flush=True)
