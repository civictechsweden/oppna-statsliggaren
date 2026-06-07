from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import sys

import mdformat
from markdownify import markdownify as md

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.cleaner import Cleaner


def convert(path: Path) -> tuple[str, str]:
    xhtml = path.read_text(encoding="utf-8")
    markdown = Cleaner.clean_markdown(
        mdformat.text(
            md(xhtml, heading_style="ATX"),
            options={"number": True},
        )
    )
    return path.stem, markdown


def main() -> None:
    root = Path("letters/xhtml")
    out_root = Path("letters/md")
    out_root.mkdir(parents=True, exist_ok=True)

    paths = sorted(root.glob("*.xhtml"), key=lambda path: int(path.stem))
    count = 0

    with ProcessPoolExecutor() as pool:
        for stem, markdown in pool.map(convert, paths, chunksize=32):
            (out_root / f"{stem}.md").write_text(markdown, encoding="utf-8")
            count += 1
            if count % 1000 == 0:
                print(f"converted {count}", flush=True)

    print(f"regenerated {count} markdown files")


if __name__ == "__main__":
    main()
