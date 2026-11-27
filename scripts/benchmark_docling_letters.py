"""Benchmark fresh XHTML against the real Docling service, without publishing.

Run ``uv run -m scripts.benchmark_docling_letters --output-directory
letters/docling-quality``. Raw HTML is read from letters/html; no dataset download
or stale XHTML cache is used. Default sample: two letters per source template.
"""

import argparse
import asyncio
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import time
import unicodedata
from xml.etree import ElementTree as ET

import httpx

from scripts.rebuild_letters import _heading_text, _local_name
from services.intermediate_parser import IntermediateParser
from services.template_classifier import classify_letter_template


SERVICE_URL = "http://esvaiws01.esv.local:8087"
CONFIGURATION = {
    "convert_from_formats": "json_docling", "include_converted_doc": "true",
    "target_type": "inbody",
    "chunking_max_tokens": "1536",
    "chunking_tokenizer": "microsoft/harrier-oss-v1-0.6b",
    "chunking_merge_peers": "true", "chunking_include_raw_text": "true",
    "chunking_use_markdown_tables": "true",
}
CONVERSION_CONFIGURATION = {
    "from_formats": "html", "to_formats": ["json", "md", "text"],
    "image_export_mode": "placeholder", "target_type": "inbody",
}


def _canonical(text):
    # Lexical coverage tolerates formatting, soft hyphens, and wrapped lines.
    return "".join(c for c in unicodedata.normalize("NFKC", text) if c.isalnum()).casefold()


def expected_content(xhtml):
    body = ET.fromstring(xhtml).find("{*}body")
    paragraphs, cells, spans, headings, content_paths = [], [], [], [], []
    active, stack = False, []

    def walk(node):
        nonlocal active, stack
        name = _local_name(node.tag)
        text = " ".join(_heading_text(node).split())
        if re.fullmatch(r"h[1-6]", name):
            active = True
            level = int(name[1])
            stack = [(n, t) for n, t in stack if n < level] + [(level, text)]
            headings.append([title for _, title in stack])
            return
        if not active and name == "table":
            return  # Letterhead furniture precedes the document title.
        if name == "table":
            for cell in node.iter():
                if _local_name(cell.tag) in {"th", "td"}:
                    value = " ".join(_heading_text(cell).split())
                    if value:
                        cells.append(value)
                        content_paths.append([title for _, title in stack])
                    row, col = int(cell.get("rowspan", 1)), int(cell.get("colspan", 1))
                    if row > 1 or col > 1:
                        spans.append({"text": value, "row_span": row, "col_span": col})
            return
        if active and (name == "p" or (name == "li" and node.find(".//{*}p") is None)):
            if text:
                paragraphs.append(text)
                content_paths.append([title for _, title in stack])
            return
        if active and node.text and node.text.strip():
            paragraphs.append(" ".join(node.text.split()))
            content_paths.append([title for _, title in stack])
        for child in node:
            walk(child)
            if active and child.tail and child.tail.strip():
                paragraphs.append(" ".join(child.tail.split()))
                content_paths.append([title for _, title in stack])

    walk(body)
    return {"paragraphs": paragraphs, "cells": cells, "spans": spans,
            "headings": headings, "content_paths": content_paths}


def evaluate(xhtml, result):
    """Report lexical omissions and structure differences, never infer success from counts."""
    expected = expected_content(xhtml)
    document = result["documents"][0]["content"]["json_content"]
    chunks = result["chunks"]
    tables = [t for t in document.get("tables", []) if t.get("content_layer") != "furniture"]
    doc_cells = [c for table in tables for c in table["data"]["table_cells"]]
    doc_text = "\n".join(
        [t.get("text", "") for t in document.get("texts", []) if t.get("content_layer") != "furniture"]
        + [c.get("text", "") for c in doc_cells]
    )
    raw_text = "\n".join(c.get("raw_text", "") for c in chunks)
    doc_canonical, chunk_canonical = _canonical(doc_text), _canonical(raw_text)

    def missing(values, haystack):
        return [text for text in values if _canonical(text) and _canonical(text) not in haystack]

    # Match complete values independently: serialized Markdown repeats spanning cells.
    numeric = [t for t in expected["cells"] if re.fullmatch(r"[\d\s%.,+\-–−()]+", t) and re.search(r"\d", t)]
    expected_paths = [tuple(map(_canonical, path)) for path in expected["headings"]]
    actual_paths = [tuple(map(_canonical, c.get("headings") or [])) for c in chunks]
    absent_paths = [path for path, normalized in zip(expected["headings"], expected_paths)
                    if not any(actual[:len(normalized)] == normalized for actual in actual_paths)]
    content_paths = {tuple(map(_canonical, path)) for path in expected["content_paths"]}
    substantive_absent_paths = [path for path in absent_paths if tuple(map(_canonical, path)) in content_paths]
    empty_absent_paths = [path for path in absent_paths if tuple(map(_canonical, path)) not in content_paths]
    unknown_paths = [c.get("headings") for c, path in zip(chunks, actual_paths)
                     if path and path not in expected_paths]
    actual_spans = [{"text": c.get("text", ""), "row_span": c["row_span"], "col_span": c["col_span"]}
                    for c in doc_cells if c.get("row_span", 1) > 1 or c.get("col_span", 1) > 1]
    span_counts = Counter((_canonical(s["text"]), s["row_span"], s["col_span"]) for s in actual_spans)
    missing_spans = []
    for span in expected["spans"]:
        key = (_canonical(span["text"]), span["row_span"], span["col_span"])
        if span_counts[key]:
            span_counts[key] -= 1
        else:
            missing_spans.append(span)
    issues = {
        "paragraphs_missing_from_document": missing(expected["paragraphs"], doc_canonical),
        "paragraphs_missing_from_chunks": missing(expected["paragraphs"], chunk_canonical),
        "table_cells_missing_from_document": missing(expected["cells"], doc_canonical),
        "table_cells_missing_from_chunks": missing(expected["cells"], chunk_canonical),
        "numeric_cells_missing_from_chunks": missing(numeric, chunk_canonical),
        "heading_paths_missing_from_chunks": substantive_absent_paths,
        "headings_missing_from_document": missing([p[-1] for p in expected["headings"]], doc_canonical),
        "unexpected_chunk_heading_paths": unknown_paths,
        "spans_missing_from_document": missing_spans,
        "over_budget_chunks": [c["chunk_index"] for c in chunks if c["num_tokens"] > 1536],
        "empty_chunks": [c["chunk_index"] for c in chunks if not c.get("raw_text", "").strip()],
        "document_errors": [d.get("errors") for d in result["documents"] if d.get("errors")],
        "unsuccessful_documents": [d.get("status") for d in result["documents"]
                                   if d.get("status") not in {None, "success"}],
        "spanning_tables_missing_chunk_references": [t["self_ref"] for t in tables
            if t.get("self_ref") and any(c.get("row_span", 1) > 1 or c.get("col_span", 1) > 1
                                        for c in t["data"]["table_cells"])
            and not any(t["self_ref"] in c.get("doc_items", []) for c in chunks)],
    }
    return {
        "status": "review" if any(issues.values()) or not chunks else "ok",
        "chunks": len(chunks), "max_tokens": max((c["num_tokens"] for c in chunks), default=0),
        "tiny_chunks_under_200_chars": sum(len(c.get("raw_text", "")) < 200 for c in chunks),
        "expected_paragraphs": len(expected["paragraphs"]), "expected_table_cells": len(expected["cells"]),
        "expected_heading_paths": len(expected_paths), "expected_spans": len(expected["spans"]),
        "document_spans": len(actual_spans), "issues": issues,
        "diagnostics": {"empty_section_heading_paths_absent_from_chunks": empty_absent_paths},
        "span_serialization": "Text chunks serialize cells without span geometry; structured spans remain in DoclingDocument and doc_items references",
    }


def select_ids():
    selected = [240, 8103, 8899, 8187, 25867, 21417]
    counts = Counter(classify_letter_template(Path(f"letters/html/{i}.html").read_text()).variant for i in selected)
    with Path("letter_templates.csv").open() as handle:
        for row in csv.DictReader(handle):
            rbid = int(row["rbid"])
            if counts[row["variant"]] >= 2 or rbid in selected:
                continue
            path = Path(f"letters/html/{rbid}.html")
            if path.exists():
                variant = classify_letter_template(path.read_text()).variant
                if variant != "unknown" and counts[variant] < 2:
                    selected.append(rbid)
                    counts[variant] += 1
    if len(selected) != 14 or len(counts) != 7 or set(counts.values()) != {2}:
        raise ValueError(f"Expected two raw HTML letters per template, found {dict(counts)}")
    return selected


async def _job(client, endpoint, configuration, upload, handle_path, *, timeout=300):
    # Keep job handles immediately, allowing diagnosis/resumption if polling fails.
    request_hash = hashlib.sha256(upload[1] + json.dumps(configuration, sort_keys=True).encode()).hexdigest()
    if handle_path.exists():
        task = json.loads(handle_path.read_text())
        if task.get("request_sha256") != request_hash:
            raise ValueError("Saved job has different input/configuration; use a new output directory")
    else:
        response = await client.post(endpoint, data=configuration, files={"files": upload})
        response.raise_for_status()
        task = response.json()
        task["request_sha256"] = request_hash
        handle_path.write_text(json.dumps(task, indent=2))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = await client.get(f"/v1/status/poll/{task['task_id']}", params={"wait": 1})
        response.raise_for_status()
        status = response.json()
        if status["task_status"] in {"success", "partial_success"}:
            response = await client.get(f"/v1/result/{task['task_id']}")
            response.raise_for_status()
            return response.json()
        if status["task_status"] == "failure":
            raise RuntimeError(f"Docling job failed: {status}")
        await asyncio.sleep(1)
    raise TimeoutError(f"Docling job {task['task_id']} still pending after {timeout}s")


async def convert(client, xhtml, rbid, directory, *, timeout=300):
    converted = await _job(client, "/v1/convert/file/async", CONVERSION_CONFIGURATION,
                           (f"{rbid}.html", xhtml.encode(), "text/html"),
                           directory / f"{rbid}.convert.task.json", timeout=timeout)
    (directory / f"{rbid}.converted.json").write_text(json.dumps(converted, ensure_ascii=False, indent=2))
    document = converted["document"]["json_content"]
    return await _job(client, "/v1/chunk/hybrid/file/async", CONFIGURATION,
                      ("document.json", json.dumps(document, ensure_ascii=False).encode(), "application/json"),
                      directory / f"{rbid}.chunk.task.json", timeout=timeout)


async def benchmark(ids, directory, service_url=SERVICE_URL):
    started = time.monotonic()
    directory.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(2)
    async with httpx.AsyncClient(base_url=service_url, timeout=60) as client:
        response = await client.get("/version")
        response.raise_for_status()
        summary = {"service_url": service_url, "versions": response.json(),
                   "configuration": CONFIGURATION, "conversion_configuration": CONVERSION_CONFIGURATION,
                   "concurrency": 2, "results": []}
        summary["parser_files_sha256"] = {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [Path("services/intermediate_parser.py"), Path("services/heading_alignment.py"),
                         Path("services/source_corrections.py")]
        }

        async def one(rbid):
            async with semaphore:
                html = Path(f"letters/html/{rbid}.html").read_text()
                row = {"id": rbid, "template": str(classify_letter_template(html).variant),
                       "source_html_sha256": hashlib.sha256(html.encode()).hexdigest()}
                started = time.monotonic()
                try:
                    corrections = []
                    xhtml = IntermediateParser.parse_letter_html(html, corrections=corrections)
                    row["corrections"] = corrections
                    row["xhtml_sha256"] = hashlib.sha256(xhtml.encode()).hexdigest()
                    (directory / f"{rbid}.xhtml").write_text(xhtml)
                    result = await convert(client, xhtml, rbid, directory)
                    (directory / f"{rbid}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
                    row.update(evaluate(xhtml, result))
                except Exception as error:
                    row.update(status="failed", error=f"{type(error).__name__}: {error}")
                row["elapsed_seconds"] = round(time.monotonic() - started, 2)
                print(f"{rbid}: {row['status']} ({row['elapsed_seconds']}s)", flush=True)
                return row

        summary["results"] = await asyncio.gather(*(one(rbid) for rbid in ids))
        summary["elapsed_seconds"] = round(time.monotonic() - started, 2)
        summary["coverage_note"] = "Lexical substring coverage tolerates formatting; review reported omissions and original artifacts. Letterhead furniture is excluded. Counts alone do not demonstrate preservation."
        (directory / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
        with (directory / "summary.csv").open("w") as handle:
            fields = ["id", "template", "status", "chunks", "max_tokens", "tiny_chunks_under_200_chars",
                      "expected_heading_paths", "expected_spans", "document_spans", "issue_count", "error"]
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for row in summary["results"]:
                writer.writerow({**row, "issue_count": sum(len(v) for v in row.get("issues", {}).values())})
        return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", help="Comma-separated letter IDs; defaults to two per template")
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--service-url", default=SERVICE_URL)
    args = parser.parse_args()
    ids = [int(value) for value in args.ids.split(",")] if args.ids else select_ids()
    summary = asyncio.run(benchmark(ids, args.output_directory, args.service_url))
    raise SystemExit(any(row["status"] != "ok" for row in summary["results"]))


if __name__ == "__main__":
    main()
