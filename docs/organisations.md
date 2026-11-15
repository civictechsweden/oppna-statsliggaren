# Organisation identities and collective recipients

`organisations.json` is the published registry. `letters.csv` stores its recipient
IDs in the semicolon-separated `organisation_ids` column; Parquet stores the same
values as `list<int32>`. Original letter names, HTML, XHTML and Markdown remain
unchanged. Consumers should fetch the registry and Parquet at the same HF revision.

## Identity and name history

There is one registry entry per **Statsliggaren source ID**. The number comes from
agency links such as `/statsliggaren/regleringsbrev/187/2026/senaste`, not from
`RBID`, which identifies a letter/version. These are source-entry identifiers,
not Swedish organisationsnummer or a general legal-entity register.

An organisation record contains `id`, `statsliggaren_id`, `display_name` and
`names`. Native IDs are reused unchanged. Exact historical spellings are retained
in `names`, including case variants. The name on each letter is also preserved.
`display_name` selects the most recently observed name as a convenient label.

The `from_year` and `to_year` in **automatically acquired names** describe the
first and last source years observed, not independently verified legal validity.
Their interval can contain gaps or retrospective wording. The separate
`name_periods` section records the researched university-name periods below;
its open ends use `null`. Neither kind of range describes institution founding
dates: this corpus starts in 2003.

Different source IDs are never merged merely because their names match. For
example, Skatteverket has two source entries in 2004. Its original
[RBID 5112](https://www.statskontoret.se/statsliggaren/regleringsbrev/?RBID=5112)
uses ID 1057, while amendments
[7149](https://www.statskontoret.se/statsliggaren/regleringsbrev/?RBID=7149) and
[7719](https://www.statskontoret.se/statsliggaren/regleringsbrev/?RBID=7719) expose
ID 422 in their public year-navigation links. The reviewed `letter_source_ids`
exceptions preserve this distinction during the initial backfill.

Local IDs occupy the reserved range starting at 1,000,000 and have
`statsliggaren_id: null`. They are fixed values in the curated input, never
generated from row positions at runtime. IDs 1000001–1000021 identify the
individual county boards. IDs 1000022–1000024 identify Riksdagsförvaltningen,
Riksdagens ombudsmän JO and Riksrevisionen: their inspected public pages expose
no recoverable source ID. This does not assert that Hermes has no private ID.
An upstream ID entering the local range stops generation for review rather than
silently changing existing identities.

## What the generator acquires automatically

Run:

```sh
uv run -m scripts.build_organisations --parquet letters.parquet
```

`services/organisations.py` fetches the public annual agency indexes for the
years in the catalogue, extracts native IDs and names from the links, and merges
those observations into the existing registry. It never deletes older names.
The initial 2003–2026 acquisition found 318 source entries, including the two
collective entries; collectives are represented separately rather than exported
as individual recipient organisations.

Five historical catalogue spellings need reviewed aliases to source entries.
Their IDs were checked against the public letter's year-navigation links:
RBIDs 484 → 155, 7680 → 335, 449 → 175, 429 → 167, and 379 → 494.
They are recorded in `source_aliases`, not inferred by fuzzy name matching.

Normal scraping reads the source ID from each refreshed letter's navigation.
It can record a newly encountered native entry and its exact name. For older
cached rows it uses the reviewed registry, source-year observations, and explicit
exceptions. An unknown or ambiguous organisation stops annotation for review.
Unchanged source IDs already recorded on cached rows are retained.

The generator annotates the whole CSV. Its optional Parquet pass streams the
existing file and adds/replaces only `organisation_ids`, verifying every other
column is unchanged. The normal exporter also creates a typed list column and
publishes the registry alongside Parquet in the same HF commit. PDFs and
attachments are not downloaded or reparsed by this backfill.

## How collective membership is acquired

Membership is **reviewed source data**, not an automatic extraction of every
organisation mentioned in a letter. The committed input is
`data/collective_organisations.json`; the generator copies its `collectives` and
`name_periods` into the published registry. A member has `organisation_id`,
inclusive `from_year`, and inclusive `to_year` (`null` means ongoing).

### County boards: collective source ID 1015

The 21 individual organisations come from the national
[Länsstyrelserna roster](https://www.lansstyrelsen.se/), reviewed in November 2026.
They use fixed local IDs because Statsliggaren's public agency index exposes
the collective entry `länsstyrelserna`. The committed membership covers the
2003-onward corpus. The generator does not infer county recipients from copy
lists, geographical words, or mentions of a board in the body.

### Universities and colleges: collective source ID 1016

All 45 researched historical university names have native IDs. Six renames reuse
an ID, giving **39 source identities**, not 45 newly generated institutions.
Their common-letter membership is curated from these sources:

- [UKÄ's institution-history workbook, January 2026](https://www.uka.se/download/18.4e1e1cc819b2c0041ba1cc/1769519412610/UH-lista-2026-01.xlsx), linked from
  [Information om statistiken](https://www.uka.se/statistik-och-analys/om-var-statistik/information-om-statistiken),
  provides the state/private distinction and rename/merger dates. These facts
  were reviewed into the committed periods; the generator does not attempt to
  interpret free-text workbook notes at runtime.
- [The 2006 letter, RBID 9185](https://www.statskontoret.se/statsliggaren/regleringsbrev/?RBID=9185)
  names 35 individual state institutions in annexes. Its roster, the historical
  UKÄ names and the verified changes reconstruct the earlier corpus years.
- Named institution annexes in 2006–2010 and the direct `Likalydande till` lists
  in 2011–2013 were compared with the resulting annual rosters. The lists are
  evidence, not unconditional input: the 2008 direct list omits Högskolan
  Kristianstad despite its named annex.
- The 2008 letter also retains a Lärarhögskolan annex after its January merger.
  [Annex 39](https://huggingface.co/datasets/PierreMesure/oppna-statsliggaren/resolve/51498bbfd6fb4e7bbc44201500a7f03c8ab77c65/attachments/2008/2753.docx)
  transfers 2007 appropriation savings to Stockholms universitet; it does not
  establish a continuing independent 2008 recipient.
- [UKÄ/SCB's 2017/18 statistical report, p.112](https://www.uka.se/download/18.3024c77018b37fb62411a9d0/1697549198758/2019-04-17-Statistiskt-meddelande-Studenter-och%20examinerade-pa-grundniva-och%20avancerad%20niva-%202017-2018.pdf)
  and [SKH's archive description, p.3](https://litium.uniarts.se/storage/ma/e895a82796f94d3a8c26478bf35be3d5/1ccee451fa96408aaf2cc9ea30c52e5f/pdf/3F5FF72159A1FFC72A6146CF2BF7E0AD479D6C56/Arkivbeskrivning%20SKH%20AB%203_0.pdf)
  confirm Danshögskolan's January 2010 rename. A stale annex heading is not used
  to override that history.
- Försvarshögskolan's common-letter range starts in **2009**, when it has a
  named annex. Its 2008 change of institutional status is insufficient evidence:
  [the 2008 common letter](https://www.statskontoret.se/statsliggaren/regleringsbrev/?RBID=11434)
  only copies it, while its [separate 2008 letter](https://www.statskontoret.se/statsliggaren/regleringsbrev/?RBID=10776)
  contains its activity instructions.
- SLU and private providers are excluded from this common-provisions roster.
  [The 2026 letter](https://www.statskontoret.se/statsliggaren/regleringsbrev/?RBID=26223)
  expressly excludes SLU while still copying it. Earlier funding references and
  private-provider contracts do not automatically make those institutions
  recipients of the common provisions. This is not general entity extraction
  for every beneficiary in a decision.

Use the **original chain's budget year**, not the latest amendment's calendar
year. RBID 12572 was issued in January 2010 but belongs to the 2009 chain, so it
keeps Växjö and Kalmar rather than gaining Linnéuniversitetet prematurely.
Include institutions active during any part of a budget year. Gotland is thus
included for 2013 but not 2014. GIH's 2005 rename preserves both names but emits
source ID 255 only once. The original 24 collective chains contain 83 versions.

## Maintenance and scope

Review institutional changes against the linked primary sources, update the
curated file with the evidence and effective budget years, regenerate, then
review the JSON/CSV diff and run `uv run -m unittest discover -s tests`.
An open end is a maintained assumption, not an automatic discovery of future
mergers. Never renumber existing IDs or replace name history with a latest-name
dictionary. The generator preserves each original letter name separately.

Ordinary agency letters receive their source entry ID. Appropriation letters
currently have an empty list: their financial title is not assumed to identify
an organisation. An empty list means no recipient assignment was made here,
not that the decision has no real-world recipients.
