import copy
import csv
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq

from scripts.build_letters_parquet import _metadata_value
from scripts import build_letters_parquet as builder
from scripts.build_organisations import update_parquet
from services.organisations import (
    acquire_registry,
    assign_organisation_ids,
    finish_registry,
    load_registry,
    observe_name,
    source_organisation_id,
    validate_registry,
    ROOT,
)


def row(rbid, name, year=2026, category="Myndighet", **kwargs):
    return dict(
        rbid=rbid, original_rbid=rbid, name=name, year=year, category=category, **kwargs
    )


class OrganisationTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry()

    def assign(self, rows):
        assign_organisation_ids(rows, self.registry)
        return [
            [int(value) for value in r["organisation_ids"].split(";") if value]
            for r in rows
        ]

    def test_source_id_is_distinct_from_letter_id_and_must_be_unambiguous(self):
        self.assertEqual(
            source_organisation_id(
                '<aside id="sidebar"><a href="?RBID=25867">Brevet</a>'
                '<a href="/statsliggaren/regleringsbrev/194/2025/senaste">2025</a></aside>'
            ),
            194,
        )
        self.assertIsNone(
            source_organisation_id('<a href="/regleringsbrev/194/2025/senaste">194</a>')
        )
        self.assertIsNone(
            source_organisation_id(
                '<aside id="sidebar"><a href="/regleringsbrev/1/2025/senaste">1</a>'
                '<a href="/regleringsbrev/2/2025/senaste">2</a></aside>'
            )
        )

    def test_renames_keep_native_id_and_every_original_letter_name(self):
        rows = [row(1, "Malmö Högskola", 2003), row(2, "Malmö universitet")]
        self.assertEqual(self.assign(rows), [[187], [187]])
        self.assertEqual(
            [r["name"] for r in rows], ["Malmö Högskola", "Malmö universitet"]
        )
        organisation = next(
            item for item in self.registry["organisations"] if item["id"] == 187
        )
        self.assertTrue(
            {r["name"] for r in rows}
            <= {entry["name"] for entry in organisation["names"]}
        )

    def test_same_name_source_entries_are_not_merged(self):
        rows = [
            row(5112, "Skatteverket", 2004),
            row(7149, "Skatteverket", 2004),
            row(7719, "Skatteverket", 2004),
        ]
        self.assertEqual(self.assign(rows), [[1057], [422], [422]])

    def test_fresh_page_identity_takes_precedence_over_inference(self):
        rows = [row(99, "Skatteverket", 2004, _source_organisation_id=1057)]
        self.assertEqual(self.assign(rows), [[1057]])
        self.assertNotIn("_source_organisation_id", rows[0])

    def test_new_source_entry_is_recorded_without_reassigning_existing_ids(self):
        rows = [row(99, "Ny myndighet", _source_organisation_id=99999)]
        self.assertEqual(self.assign(rows), [[99999]])
        self.assertEqual(self.registry["organisations"][-1]["statsliggaren_id"], 99999)

    def test_unknown_name_fails_instead_of_guessing(self):
        with self.assertRaisesRegex(ValueError, "Unresolved organisation"):
            self.assign([row(99, "Okänd myndighet")])

    def test_county_collective_expands_to_21_marked_local_ids(self):
        (ids,) = self.assign([row(99, "LÄNSSTYRELSERNA")])
        self.assertEqual(ids, list(range(1000001, 1000022)))
        local = {item["id"]: item for item in self.registry["organisations"]}
        self.assertTrue(all(local[key]["statsliggaren_id"] is None for key in ids))

    def test_university_collective_uses_original_budget_year_for_late_amendment(self):
        rows = [
            row(11452, "universitet och högskolor m.m.", 2009),
            {
                **row(12572, "universitet och högskolor m.m.", 2010),
                "original_rbid": 11452,
            },
        ]
        original, amendment = self.assign(rows)
        self.assertEqual(original, amendment)
        self.assertTrue({184, 186} <= set(original))
        self.assertNotIn(1162, original)

    def test_midyear_rename_does_not_duplicate_the_same_source_identity(self):
        (ids,) = self.assign([row(99, "universitet och högskolor", 2005)])
        self.assertEqual(ids.count(255), 1)
        self.assertEqual(len(ids), 35)

    def test_midyear_merger_keeps_gotland_for_2013_but_not_2014(self):
        before, after = self.assign(
            [
                row(1, "universitet och högskolor", 2013),
                row(2, "universitet och högskolor", 2014),
            ]
        )
        gotland = next(
            item["id"]
            for item in self.registry["organisations"]
            if item["display_name"] == "Högskolan på Gotland"
        )
        self.assertIn(gotland, before)
        self.assertNotIn(gotland, after)
        self.assertIn(262, before)
        self.assertIn(262, after)

    def test_defence_membership_and_exclusions_come_from_curated_data(self):
        before, after, current = self.assign(
            [
                row(1, "universitet och högskolor", 2008),
                row(2, "universitet och högskolor", 2009),
                row(3, "universitet och högskolor"),
            ]
        )
        self.assertNotIn(484, before)
        self.assertIn(484, after)
        self.assertEqual(len(current), 30)
        self.assertNotIn(191, current)  # SLU is copied, not in the common roster.

    def test_appropriation_titles_do_not_create_organisation_ids(self):
        self.assertEqual(
            self.assign([row(1, "universitet och högskolor", category="Anslag")]), [[]]
        )

    def test_observations_never_remove_previous_names(self):
        item = {"id": 1, "statsliggaren_id": 1, "display_name": "Gammalt", "names": []}
        observe_name(item, "Gammalt", 2003)
        observe_name(item, "Nytt", 2026)
        registry = {"organisations": [item]}
        finish_registry(registry)
        self.assertEqual(item["display_name"], "Nytt")
        self.assertEqual(
            {entry["name"] for entry in item["names"]}, {"Gammalt", "Nytt"}
        )

    def test_registry_rejects_duplicate_ids_and_dangling_memberships(self):
        self.registry["organisations"].append(
            copy.deepcopy(self.registry["organisations"][0])
        )
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            validate_registry(self.registry)
        self.registry["organisations"].pop()
        self.registry["collectives"][0]["members"][0]["organisation_id"] = -1
        with self.assertRaisesRegex(ValueError, "unknown"):
            validate_registry(self.registry)

    def test_published_catalogue_references_exist_and_preserve_name_history(self):
        validate_registry(self.registry)
        by_id = {item["id"]: item for item in self.registry["organisations"]}
        with (ROOT / "letters.csv").open() as handle:
            for item in csv.DictReader(handle):
                ids = [
                    int(value) for value in item["organisation_ids"].split(";") if value
                ]
                self.assertTrue(set(ids) <= by_id.keys())
                if len(ids) == 1:
                    self.assertIn(
                        item["name"],
                        {entry["name"] for entry in by_id[ids[0]]["names"]},
                    )

    def test_parquet_backfill_preserves_all_previous_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "letters.parquet"
            original = pa.table(
                {
                    "id": [1, 2],
                    "name": ["Äldre namn", "Anslag"],
                    "md": ["# Hej", "Text"],
                }
            )
            pq.write_table(original, path)
            rows = [
                dict(rbid=1, organisation_ids="187;255"),
                dict(rbid=2, organisation_ids=""),
            ]
            update_parquet(path, rows)
            updated = pq.read_table(path)
            self.assertTrue(updated.select(original.column_names).equals(original))
            self.assertEqual(updated["organisation_ids"].to_pylist(), [[187, 255], []])
            self.assertEqual(
                updated.schema.field("organisation_ids").type, pa.list_(pa.int32())
            )
            self.assertEqual(_metadata_value("organisation_ids", "187;255"), [187, 255])

    def test_export_rejects_dangling_ids_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "organisations.json").write_text(json.dumps(self.registry))
            output = root / "letters.parquet"
            with (
                patch("sys.argv", ["builder", "--output", str(output)]),
                patch.object(builder, "ROOT", root),
                patch.object(
                    builder,
                    "_load_metadata",
                    return_value=(
                        ["organisation_ids"],
                        {1: {"organisation_ids": "9999999"}},
                    ),
                ),
            ):
                with self.assertRaisesRegex(ValueError, "Unknown organisation IDs"):
                    builder.main()
            self.assertFalse(output.exists())


class AcquisitionTests(unittest.IsolatedAsyncioTestCase):
    async def test_annual_index_acquisition_preserves_older_observations(self):
        rules = {
            "local_organisations": [],
            "source_aliases": {},
            "letter_source_ids": {},
            "name_periods": [],
            "sources": {},
            "collectives": [],
        }
        pages = {
            2003: '<a href="/statsliggaren/regleringsbrev/200/2003/senaste">Mitthögskolan</a>',
            2026: '<a href="/statsliggaren/regleringsbrev/200/2026/senaste">Mittuniversitetet</a>',
        }

        class Downloader:
            async def _get_with_retry(self, url):
                return SimpleNamespace(text=pages[int(url.rsplit("=", 1)[1])])

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rules.json"
            path.write_text(json.dumps(rules))
            registry = await acquire_registry(Downloader(), {2003}, rules_path=path)
            registry = await acquire_registry(
                Downloader(), {2026}, registry, rules_path=path
            )
        finish_registry(registry)
        self.assertEqual(len(registry["organisations"]), 1)
        item = registry["organisations"][0]
        self.assertEqual(item["id"], 200)
        self.assertEqual(item["display_name"], "Mittuniversitetet")
        self.assertEqual(
            {entry["name"] for entry in item["names"]},
            {"Mitthögskolan", "Mittuniversitetet"},
        )
