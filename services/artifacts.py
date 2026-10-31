"""Download and publish the original letter PDFs and attachment files."""

import asyncio
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from zipfile import ZipFile

from huggingface_hub import RepoFile

from services.downloader import DOMAIN, Downloader


def file_specs(metadata, attachments, refreshed_ids):
    specs = {}
    for rbid, row in metadata.items():
        if str(row["pdf"]).lower() == "true":
            path = f"letters/{row['year']}/{rbid}.pdf"
            specs[path] = (f"{DOMAIN}/regleringsbrev/{rbid}/pdf?Version=HelaBrevet", rbid in refreshed_ids)
    for row in attachments:
        extension = Path(row["name"]).suffix.lower()
        if not extension or not extension[1:].isalnum():
            raise ValueError(f"Attachment {row['id']} has no usable file extension: {row['name']}")
        path = f"attachments/{metadata[int(row['rbid'])]['year']}/{int(row['id'])}{extension}"
        refresh = int(row["rbid"]) in refreshed_ids or specs.get(path, (None, False))[1]
        specs[path] = (f"{DOMAIN}/regleringsbrev/bilaga/{int(row['id'])}", refresh)
    return specs


async def download_files(specs, directory: Path, existing_paths: set[str]):
    directory.mkdir(parents=True, exist_ok=True)
    downloader = Downloader()
    semaphore = asyncio.Semaphore(6)
    paths = []
    unavailable = []

    async def download(path, url, refresh):
        if path in existing_paths and not refresh:
            return
        target = directory / path
        async with semaphore:
            old_target = directory / ("pdf" if path.startswith("letters/") else "attachments") / Path(path).name
            if old_target.exists() and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                old_target.replace(target)
            if not target.exists() or refresh:
                response = await downloader._get_with_retry(url)
                if response.status_code == 404 or not response.content:
                    unavailable.append({"path": path, "url": url, "status": response.status_code,
                                        "reason": "not_found" if response.status_code == 404 else "empty_response"})
                    return
                data = response.content
                content_type = response.headers.get("content-type", "").lower()
                if "text/html" in content_type:
                    raise ValueError(f"Expected a document file at {url}, received {content_type}")
                if path.startswith("letters/") and not data.startswith(b"%PDF"):
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
    unavailable.sort(key=lambda item: item["path"])
    if unavailable:
        print(f"Source files unavailable: {unavailable}", flush=True)
    (directory / "unavailable_files.json").write_text(json.dumps(unavailable, ensure_ascii=False, indent=2))
    return sorted(paths)


def converted_path(path: str) -> str | None:
    extension = Path(path).suffix
    if path.startswith("attachments/") and extension in (".doc", ".xls"):
        return str(Path(path).with_suffix(extension + "x"))
    return None


def files_to_publish(paths, directory: Path, remote_files):
    changed = []
    conversions = []
    for path in paths:
        source = directory / path
        remote = remote_files.get(path)
        same = False
        if remote and source.stat().st_size == remote.size:
            if remote.lfs:
                digest = hashlib.sha256()
                expected = remote.lfs.sha256
            else:
                digest = hashlib.sha1(f"blob {remote.size}\0".encode())
                expected = remote.blob_id
            with source.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            same = digest.hexdigest() == expected
        if not same:
            changed.append(path)
        derivative = converted_path(path)
        if derivative and (not same or derivative not in remote_files):
            conversions.append(path)
    return changed, conversions


async def fetch_source_files(metadata, attachments, refreshed_ids, api, repo_id: str, directory: Path):
    api.create_repo(repo_id=repo_id, repo_type="dataset", exist_ok=True)
    remote_files = {
        item.path: item for item in api.list_repo_tree(
            repo_id=repo_id, repo_type="dataset", recursive=True
        ) if isinstance(item, RepoFile)
    }
    specs = file_specs(metadata, attachments, refreshed_ids)
    reusable_paths = {
        path for path in remote_files
        if not converted_path(path) or converted_path(path) in remote_files
    }
    downloaded = await download_files(specs, directory, reusable_paths)
    changed, conversions = files_to_publish(downloaded, directory, remote_files)
    (directory / "source_files.json").write_text(json.dumps({
        "paths": changed,
        "conversions": conversions,
    }, indent=2))
    print(f"Fetched {len(downloaded)} files; {len(changed)} changed, {len(conversions)} need conversion")


def convert_attachments(directory: Path, paths: list[str]) -> list[str]:
    """Create OOXML derivatives without changing the original attachments."""
    converted = []
    pending = []
    for source in paths:
        target = converted_path(source)
        if not target:
            continue
        output = directory / target
        if output.exists() and output.stat().st_mtime_ns >= (directory / source).stat().st_mtime_ns:
            converted.append(target)
        else:
            pending.append(source)

    def convert_batch(batch):
        extension = Path(batch[0]).suffix
        member = "word/document.xml" if extension == ".doc" else "xl/workbook.xml"
        with tempfile.TemporaryDirectory(prefix="statsliggaren-office-") as temporary:
            root = Path(temporary)
            subprocess.run(
                ["libreoffice", f"-env:UserInstallation={(root / 'profile').as_uri()}",
                 "--headless", "--convert-to", extension[1:] + "x", "--outdir", str(root),
                 *(str((directory / path).resolve()) for path in batch)],
                check=True, capture_output=True, text=True, timeout=600,
            )
            outputs = []
            for source in batch:
                target = converted_path(source)
                output = root / Path(target).name
                if not output.exists():
                    raise RuntimeError(f"LibreOffice did not convert {source}")
                with ZipFile(output) as archive:
                    if member not in archive.namelist():
                        raise ValueError(f"Invalid converted Office document: {source}")
                output.replace(directory / target)
                outputs.append(target)
            return outputs

    batches = []
    for extension in (".doc", ".xls"):
        sources = [path for path in pending if Path(path).suffix == extension]
        batches.extend(sources[offset:offset + 50] for offset in range(0, len(sources), 50))
    with ThreadPoolExecutor(max_workers=4) as pool:
        for outputs in pool.map(convert_batch, batches):
            converted.extend(outputs)
            print(f"Converted {len(converted)} legacy Office attachments", flush=True)
    return converted


def convert_pending_attachments(directory: Path) -> None:
    manifest = directory / "source_files.json"
    data = json.loads(manifest.read_text())
    converted = convert_attachments(directory, data["conversions"])
    data["paths"] = sorted(set(data["paths"] + converted))
    data["conversions"] = []
    manifest.write_text(json.dumps(data, indent=2))
