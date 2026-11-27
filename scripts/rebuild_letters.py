"""Rebuild derived letter content from a local, pinned Parquet snapshot.

Run with ``uv run -m scripts.rebuild_letters --source snapshot.parquet
--output letters.parquet --report rebuild-report.json``. This command neither
downloads nor publishes data. The source file's SHA256 identifies the snapshot.
"""

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import tempfile
from xml.etree import ElementTree

import mdformat
from markdown_it import MarkdownIt
from markdownify import markdownify
import pyarrow as pa
import pyarrow.parquet as pq

from services.cleaner import Cleaner
from services.intermediate_parser import IntermediateParser


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _heading_text(node) -> str:
    text = node.text or ""
    for child in node:
        text += (" " if _local_name(child.tag) == "br" else _heading_text(child)) + (child.tail or "")
    return text


def _headings(node) -> list[tuple[int, str]]:
    name = _local_name(node.tag)
    # Markdown tables represent cell headings as inline labels, not sections.
    if name == "table":
        return []
    result = []
    if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        result.append((int(name[1]), " ".join(_heading_text(node).split())))
    for child in node:
        result.extend(_headings(child))
    return result


def _convert(row):
    corrections = []
    xhtml = IntermediateParser.parse_letter_html(row["html"], corrections=corrections)
    markdown = Cleaner.clean_markdown(
        mdformat.text(markdownify(xhtml, heading_style="ATX"), options={"number": True})
    )
    document = ElementTree.fromstring(xhtml)
    if not markdown.strip() or not "".join(document.itertext()).strip():
        raise ValueError(f"Empty derived content for letter {row['id']}")
    expected = _headings(document)
    tokens = MarkdownIt("commonmark").parse(markdown)
    actual = []
    for index, token in enumerate(tokens):
        if token.type == "heading_open":
            title = "".join(
                " " if child.type in {"softbreak", "hardbreak"} else child.content
                for child in tokens[index + 1].children
                if child.type not in {
                    "em_open", "em_close", "strong_open", "strong_close",
                    "link_open", "link_close",
                }
            )
            actual.append((int(token.tag[1]), " ".join(title.split())))
    if actual != expected:
        raise ValueError(f"Markdown headings differ from XHTML for letter {row['id']}")
    return {**row, "xhtml": xhtml, "md": markdown}, corrections, Counter(level for level, _ in expected)


def _sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def rebuild(source: Path, output: Path, *, report_path: Path | None = None,
            workers: int = 4, batch_size: int = 128) -> dict:
    if workers < 1 or batch_size < 1:
        raise ValueError("workers and batch_size must be positive")
    source_hash = _sha256(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent, prefix=f".{output.name}.",
                                     suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
    report = {
        "source_sha256": source_hash, "rows": 0,
        "changed": {"xhtml": 0, "md": 0}, "heading_counts": {},
        "correction_counts": {}, "corrections_by_letter": {},
        "original_fields_unchanged": True,
        "heading_counts_before": {}, "heading_count_decreased": {},
        "multiple_document_titles": [],
    }
    correction_counts = Counter()
    heading_counts = Counter()
    heading_counts_before = Counter()
    try:
        with pq.ParquetFile(source) as original:
            schema = original.schema_arrow
            required = {"id", "html", "xhtml", "md"}
            if not required <= set(schema.names):
                raise ValueError(f"Missing source columns: {sorted(required - set(schema.names))}")
            untouched = [name for name in schema.names if name not in {"xhtml", "md"}]
            executor = ProcessPoolExecutor(max_workers=workers) if workers > 1 else nullcontext()
            with executor as pool, pq.ParquetWriter(temporary, schema, compression="zstd",
                                                   use_dictionary=False) as writer:
                for batch in original.iter_batches(batch_size=batch_size):
                    rows = batch.to_pylist()
                    results = pool.map(_convert, rows, chunksize=8) if pool else map(_convert, rows)
                    updated_rows = []
                    for before, (after, corrections, headings) in zip(rows, results, strict=True):
                        try:
                            previous_headings = _headings(ElementTree.fromstring(before["xhtml"]))
                        except ElementTree.ParseError:
                            previous_headings = []
                        heading_counts_before.update(level for level, _ in previous_headings)
                        if sum(headings.values()) < len(previous_headings):
                            report["heading_count_decreased"][str(after["id"])] = [
                                len(previous_headings), sum(headings.values())
                            ]
                        if headings[1] != 1:
                            report["multiple_document_titles"].append(after["id"])
                        for field in ("xhtml", "md"):
                            report["changed"][field] += before[field] != after[field]
                        if corrections:
                            report["corrections_by_letter"][str(after["id"])] = corrections
                            correction_counts.update(corrections)
                        heading_counts.update(headings)
                        updated_rows.append(after)
                    updated = pa.Table.from_pylist(updated_rows, schema=schema)
                    if not updated.select(untouched).equals(pa.Table.from_batches([batch]).select(untouched)):
                        raise ValueError("Rebuild changed original HTML or metadata")
                    writer.write_table(updated)
                    report["rows"] += len(rows)
                    if report["rows"] % 1024 == 0:
                        print(f"Rebuilt and validated {report['rows']} letters", flush=True)
            expected_rows = original.metadata.num_rows
        with pq.ParquetFile(temporary) as rebuilt:
            if rebuilt.metadata.num_rows != expected_rows or not rebuilt.schema_arrow.equals(schema, check_metadata=True):
                raise ValueError("Rebuild changed row count or schema")
        report["heading_counts"] = dict(sorted(heading_counts.items()))
        report["heading_counts_before"] = dict(sorted(heading_counts_before.items()))
        report["correction_counts"] = dict(sorted(correction_counts.items()))
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    report["output_sha256"] = _sha256(output)
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    report = rebuild(args.source, args.output, report_path=args.report, workers=args.workers)
    print(json.dumps({key: value for key, value in report.items() if key != "corrections_by_letter"}))


if __name__ == "__main__":
    main()
