import unittest
from types import SimpleNamespace

import pyarrow as pa

from scripts.build_letters_parquet import _normalize_existing_rows
from services.parser import Parser


def page(rbid: int, title: str, original: int | None = None, label: str = "Myndighet Testmyndigheten"):
    versions = ""
    if original is not None:
        versions = (
            '<aside id="sidebar"><nav class="content_menu"><ul><li><ul><li>'
            f'<a href="/index?rbid={original}">{label}</a><ul><li>'
            f'<a href="/index?rbid={rbid}">&#xC4;ndringsbeslut 2026-06-18</a>'
            '</li></ul></li></ul></li></ul></nav></aside>'
        )
    return SimpleNamespace(status_code=200, text=(
        f'<title>{title} - Statskontoret</title>{versions}'
        '<section id="letter"><div id="BrevHuvud">2026-06-18</div></section>'
    ))


class OriginalRbidTests(unittest.TestCase):
    def test_original_and_amendment_share_root(self):
        original, _, _ = Parser.parse_metadata(page(25761, "Regleringsbrev 2026 Anslag 1:1"), 25761)
        amendment, _, _ = Parser.parse_metadata(page(
            27457, "Ändringsbeslut 2026-06-18 Anslag 1:1", 25761, "Anslag 1:1"
        ), 27457)
        self.assertEqual(original["original_rbid"], 25761)
        self.assertEqual(amendment["original_rbid"], 25761)

    def test_unrelated_sidebar_does_not_invent_root(self):
        metadata, _, _ = Parser.parse_metadata(page(
            14885, "Ändringsbeslut 2012-11-29 Myndighet Testmyndigheten", 14135,
            "Anslag 1:4 Samhällsekonomi och finansförvaltning"
        ), 14885)
        self.assertIsNone(metadata["original_rbid"])

    def test_missing_version_link_is_unknown(self):
        metadata, _, _ = Parser.parse_metadata(page(
            14477, "Ändringsbeslut 2012-10-04 Myndighet Testmyndigheten"
        ), 14477)
        self.assertIsNone(metadata["original_rbid"])

    def test_parquet_adds_nullable_integer_column_without_touching_content(self):
        table = pa.Table.from_pylist([
            {"id": 1, "html": "original", "xhtml": "cleaned", "md": "markdown"},
            {"id": 2, "html": "other", "xhtml": "other", "md": "other"},
        ])
        rows, changed = _normalize_existing_rows(table, ["original_rbid"], {
            1: {"original_rbid": "1"}, 2: {"original_rbid": ""}
        })
        self.assertTrue(changed)
        self.assertEqual([row["original_rbid"] for row in rows], [1, None])
        self.assertEqual(rows[0]["md"], "markdown")
        self.assertEqual(str(pa.Table.from_pylist(rows).schema.field("original_rbid").type), "int64")
