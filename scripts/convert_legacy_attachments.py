"""Convert legacy attachments identified by the source fetch step."""

import json

from scripts.build_letters_parquet import LETTERS_DIR
from services.artifacts import convert_attachments


def main() -> None:
    manifest = LETTERS_DIR / "source_files.json"
    data = json.loads(manifest.read_text())
    converted = convert_attachments(LETTERS_DIR, data["conversions"])
    data["paths"] = sorted(set(data["paths"] + converted))
    data["conversions"] = []
    manifest.write_text(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
