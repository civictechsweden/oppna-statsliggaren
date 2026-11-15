"""Acquire Statsliggaren identities and expand explicitly researched collectives.

Source IDs identify Statsliggaren entries, not necessarily legal entities.
Curated membership/alias evidence lives in data/collective_organisations.json;
docs/organisations.md explains its acquisition and temporal interpretation.
"""

import asyncio
import json
import re
from pathlib import Path

from selectolax.lexbor import LexborHTMLParser

from services.downloader import DOMAIN

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "organisations.json"
RULES_PATH = ROOT / "data/collective_organisations.json"
SOURCE_ROUTE = re.compile(r"/regleringsbrev/(\d+)/(\d{4})/senaste")


def load_registry(path=REGISTRY_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def source_organisation_id(page: str) -> int | None:
    sidebar = LexborHTMLParser(page).css_first("#sidebar")
    ids = {
        int(match[1])
        for link in (sidebar.css("a[href]") if sidebar else [])
        if (match := SOURCE_ROUTE.search(link.attributes["href"]))
    }
    return ids.pop() if len(ids) == 1 else None


def observe_name(organisation, name, year):
    """Retain exact spellings and the first/last source years observed for each."""
    history = organisation["names"]
    entry = next((entry for entry in history if entry["name"] == name), None)
    if entry is None:
        history.append({"name": name, "from_year": year, "to_year": year})
    else:
        entry["from_year"] = min(entry["from_year"], year)
        entry["to_year"] = max(entry["to_year"], year)


async def acquire_registry(downloader, years, previous=None, rules_path=RULES_PATH):
    """Fetch annual agency indexes; membership is curated, never scraped from copies."""
    rules = load_registry(rules_path)
    if previous is not None:
        validate_registry(previous)
    registry = previous or {"organisations": []}
    organisations = {item["id"]: item for item in registry["organisations"]}
    collective_ids = {item["statsliggaren_id"] for item in rules["collectives"]}
    semaphore = asyncio.Semaphore(4)

    async def fetch(year):
        async with semaphore:
            response = await downloader._get_with_retry(
                f"{DOMAIN}/statsliggaren/?PeriodId={year}"
            )
        entries = []
        for link in LexborHTMLParser(response.text).css("a[href]"):
            match = SOURCE_ROUTE.search(link.attributes["href"])
            if match and int(match[2]) == year:
                entries.append((int(match[1]), link.text(strip=True), year))
        if not entries:
            raise ValueError(f"No organisation index entries for {year}")
        return entries

    for entries in await asyncio.gather(*(fetch(year) for year in sorted(years))):
        for source_id, name, year in entries:
            if source_id in collective_ids:
                continue
            if source_id >= 1_000_000:
                raise ValueError("Source ID conflicts with the reserved local ID range")
            item = organisations.setdefault(
                source_id,
                {
                    "id": source_id,
                    "statsliggaren_id": source_id,
                    "display_name": name,
                    "names": [],
                },
            )
            observe_name(item, name, year)
    for local in rules["local_organisations"]:
        item = organisations.setdefault(
            local["id"],
            {
                "id": local["id"],
                "display_name": local["display_name"],
                "statsliggaren_id": None,
                "names": [],
            },
        )
        if "name_observed_year" in local:
            observe_name(item, local["display_name"], local["name_observed_year"])
    for alias, source_id in rules["source_aliases"].items():
        organisations[source_id].setdefault("aliases", [])
        if alias not in organisations[source_id]["aliases"]:
            organisations[source_id]["aliases"].append(alias)
    registry.update(
        organisations=[organisations[key] for key in sorted(organisations)],
        collectives=rules["collectives"],
        letter_source_ids=rules["letter_source_ids"],
        name_periods=rules["name_periods"],
        sources=rules["sources"],
    )
    return registry


def assign_organisation_ids(rows, registry):
    """Annotate CSV rows, retaining source identities and original letter names."""
    validate_registry(registry)
    by_id = {item["id"]: item for item in registry["organisations"]}
    by_letter = {int(row["rbid"]): row for row in rows}
    collectives = {
        name.casefold(): item
        for item in registry["collectives"]
        for name in item["names"]
    }
    for row in rows:
        source_id = row.pop("_source_organisation_id", None)
        if row["category"] != "Myndighet":
            row["organisation_ids"] = ""
            continue
        name, year = row["name"], int(row["year"])
        collective = collectives.get(name.casefold())
        if collective:
            original = by_letter.get(int(row.get("original_rbid") or row["rbid"]), row)
            budget_year = int(original["year"])
            if budget_year < 2003:
                raise ValueError(
                    "Collective membership is researched from budget year 2003"
                )
            ids = [
                member["organisation_id"]
                for member in collective["members"]
                if member["from_year"] <= budget_year
                and (member["to_year"] is None or budget_year <= member["to_year"])
            ]
        else:
            if source_id is None:
                source_id = registry["letter_source_ids"].get(str(row["rbid"]))
            if source_id is None and row.get("organisation_ids"):
                (source_id,) = map(int, row["organisation_ids"].split(";"))
            if source_id is None:
                candidates = [
                    item
                    for item in by_id.values()
                    if name.casefold()
                    in {
                        item["display_name"].casefold(),
                        *(entry["name"].casefold() for entry in item["names"]),
                        *(alias.casefold() for alias in item.get("aliases", [])),
                    }
                ]
                if len(candidates) > 1:
                    exact = [
                        item
                        for item in candidates
                        if any(
                            entry["name"].casefold() == name.casefold()
                            and entry["from_year"] <= year <= entry["to_year"]
                            for entry in item["names"]
                        )
                    ]
                    candidates = exact or [
                        item
                        for item in candidates
                        if any(
                            entry["from_year"] <= year <= entry["to_year"]
                            for entry in item["names"]
                        )
                    ]
                if len(candidates) != 1:
                    raise ValueError(
                        f"Unresolved organisation for RBID {row['rbid']}: {name} ({year})"
                    )
                source_id = candidates[0]["id"]
            if source_id not in by_id:
                if source_id >= 1_000_000:
                    raise ValueError(
                        "Unexpected upstream organisation ID in local range"
                    )
                by_id[source_id] = {
                    "id": source_id,
                    "statsliggaren_id": source_id,
                    "display_name": name,
                    "names": [],
                }
                registry["organisations"].append(by_id[source_id])
            observe_name(by_id[source_id], name, year)
            ids = [source_id]
        if not ids or set(ids) - by_id.keys():
            raise ValueError(f"Invalid recipient IDs for RBID {row['rbid']}")
        row["organisation_ids"] = ";".join(map(str, sorted(set(ids))))


def finish_registry(registry):
    """Select a display label without deleting any older observations."""
    for item in registry["organisations"]:
        item["names"].sort(key=lambda entry: (entry["from_year"], entry["name"]))
        if item["statsliggaren_id"] is not None and item["names"]:
            item["display_name"] = max(
                item["names"], key=lambda entry: (entry["to_year"], entry["from_year"])
            )["name"]
    registry["organisations"].sort(key=lambda item: item["id"])


def validate_registry(registry):
    organisations = registry["organisations"]
    ids = {item["id"] for item in organisations}
    if len(ids) != len(organisations):
        raise ValueError("Duplicate organisation IDs")
    for item in organisations:
        if (
            item["statsliggaren_id"] is not None
            and item["id"] != item["statsliggaren_id"]
        ):
            raise ValueError("Native IDs must equal their Statsliggaren IDs")
        if item["statsliggaren_id"] is None and item["id"] < 1_000_000:
            raise ValueError("Local IDs must use the reserved range")
    for collective in registry["collectives"]:
        for member in collective["members"]:
            if member["organisation_id"] not in ids:
                raise ValueError("Collective refers to an unknown organisation")
            if (
                member["to_year"] is not None
                and member["to_year"] < member["from_year"]
            ):
                raise ValueError("Invalid collective membership period")
