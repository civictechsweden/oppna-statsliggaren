# Öppna Statsliggaren

This project aims at making the Swedish agencies mission letters (*regleringsbrev*) more accessible through a simple API and a [dataset on HuggingFace](https://huggingface.co/datasets/PierreMesure/oppna-statsliggaren).

Today, mission letters are made available on a web application called [*Statsliggaren*](https://www.statskontoret.se/statsliggaren) on the website of the [Agency for Financial and Public Management](https://www.statskontoret.se/english/) (*Statskontoret*, formerly *Ekonomistyrningsverket*). Discloser: They are my employer as of 2026 but this is an unrelated side-project.

It is hard to download the mission letter for a specific agency and a specific year from there as every document is given an obscure ID that gets incremented with each new document.

So this project essentially maps the IDs to these metadata, enabling someone to download what they need without scraping the website.

## Usage

For now, it's best to download the file [letters.csv](letters.csv) and process it yourself to match an agency and a year to a file ID.

You can also download the file [attachments.csv](attachments.csv) to get a list of the letters' attachments.

`letters.csv` includes `department`, the issuing department as written in the
letterhead, for both agency (`Myndighet`) and appropriation (`Anslag`) letters.
Historical names are preserved. Appropriation labels such as `1:1` are not unique
across departments; neither the name nor the department is a revision identifier.
The Parquet export includes the same column.

To backfill the column from an existing Parquet export (fetching letters absent
from the export or without a recognized department), run:

```bash
uv run -m scripts.backfill_departments --parquet letters.parquet
```

You can also download the letters in their row HTML format, in a cleaned XHTML format and in a (slightly lossy) Markdown format on [HuggingFace](https://huggingface.co/datasets/PierreMesure/oppna-statsliggaren).

The [organisation registry](organisations.json) preserves Statsliggaren entry IDs
and historical names. `organisation_ids` in the CSV is a semicolon-separated
list; Parquet uses an integer list. Collective letters resolve to individual
recipients upstream, using reviewed budget-year ranges. See the
[acquisition and maintenance documentation](docs/organisations.md) for sources
and the distinction between observed names and curated membership.

```sh
uv run -m scripts.build_organisations --parquet letters.parquet
```

The HTML normalization pipeline uses selectolax's Lexbor parser. Lexbor applies
HTML5 repairs, including implicit `tbody` elements and repaired paragraph
boundaries. Statsliggaren's empty XHTML-style `<em />` and `<strong />` tags are
closed before HTML parsing so they do not format the following text. The XHTML
keeps the letter text, links, and table-span attributes.
Beautiful Soup remains a direct dependency for letter metadata parsing and is
also used by Markdownify for Markdown conversion.

Headings remain headings through XHTML and Markdown conversion, including local
titles that were previously demoted to emphasis. Cross-generation heading roles
are aligned separately in `services/heading_alignment.py`: one document title,
major divisions, main sections, and local sections. The six-level limit keeps
deep sections at h6. Finance uses h4 for expenditure areas, h5 for appropriations,
and h6 for appropriation posts. This preserves boundaries but cannot encode every
ancestor of the deepest sections in Markdown.

Demonstrable source repairs are listed in `services/source_corrections.py` and
recorded by rule and letter in rebuild reports. These include duplicated title
introductions, invalid XML characters, heading spelling, and exact catalogue
title repairs. Markup compatibility repairs are identified separately. Original
HTML remains unchanged in the dataset.

To rebuild all derived content from a local, pinned dataset snapshot:

```bash
uv run -m scripts.rebuild_letters --source snapshot/letters.parquet \
  --output letters.parquet --report analysis/rebuild-report.json
```

The rebuild checks every XHTML/Markdown heading pair, row order, schema, and
unchanged original fields before replacing the output. It neither downloads nor
publishes data. XHTML retains table spans; Markdown tables lose span geometry.
Consumers that need it should parse XHTML and retain Docling's document model.

To check representative letters from all seven templates against a running
Docling service, use `uv run -m scripts.benchmark_docling_letters
--output-directory letters/docling-quality`. The benchmark records token budgets,
text and table coverage, heading paths, and preservation of structured spans.

Run the self-contained parser regressions with:

```bash
uv run -m unittest tests.test_selectolax_pipeline
```

The complete suite (`uv run -m unittest discover -s tests`) also expects
cached sample letters in `letters/html/`: 240, 5071, 5140, 6890, 8102, 8103,
8817, 8844, 8899, 11373, 21762, 25867, and 26297.

### Optional IP rotation

In order to fetch with a Github Action, we need to use a EU proxy. Right now, the program uses AWS API Gateway which has a large free tier.

You will not have to use it locally but if you want to you will need working AWS credentials in `.env`:

```text
USE_IP_ROTATOR=true
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
```

### Download a file with its ID

You can access a mission letter's page through this URL:

```text
https://www.statskontoret.se/statsliggaren/regleringsbrev/index?RbId={ID}
```

If a PDF version is available, you can download it at this URL:

```text
https://www.statskontoret.se/regleringsbrev/{ID}/pdf
```

If you just want the changes, you can add the parameter *version=EndastAndringar*:

```text
https://www.statskontoret.se/statsliggaren/regleringsbrev/index?RbId={ID}&version=EndastAndringar
https://www.statskontoret.se/regleringsbrev/{ID}/pdf?Version=EndastAndringar
```

Attachments are only available as files and can be downloaded at the following URL:

```text
https://www.statskontoret.se/regleringsbrev/bilaga/{ID}
```

### Parquet export

The repository can also build a Parquet export with document payload columns `id`, `html`, `xhtml`, and `md`, plus metadata columns from `letters.csv`: `original_rbid`, `type`, `date`, `year`, `category`, `name`, `department`, `expenditure_areas`, `registry_numbers`, and `pdf`. `original_rbid` is the original letter's RBID according to Statsliggaren's UO lists, or the letter's version navigation when it has no UO assignment. Source links can be wrong. `registry_numbers` contains individual registry numbers expanded from the letterhead's comma-separated shorthand. Omitted unit codes stay omitted unless independently documented. The CSV separates numbers with semicolons; Parquet stores them as a list of strings.
Run it locally with:

```bash
uv run -m scripts.build_letters_parquet --output letters.parquet
```

If you want to upload the result to Hugging Face, set `HF_TOKEN` and pass a dataset repo id:

```bash
HF_TOKEN=... uv run -m run --refresh-since 2025-01-01 --repo-id your-org/your-dataset
uv run -m run --convert-attachments
HF_TOKEN=... uv run -m scripts.build_letters_parquet --output letters.parquet --upload --repo-id your-org/your-dataset --repo-path letters.parquet
```

The builder also loads `.env` automatically if it exists, so local runs can use `HF_TOKEN` and `HF_DATASET_REPO_ID` from there without extra shell exports. Upload is still explicit: it only happens when `--upload` is passed.

If the local Parquet file does not exist but a Hugging Face dataset repo is configured, the script first downloads the existing remote Parquet file and then replaces locally refreshed letter payloads, fills missing payloads, and updates the CSV metadata before uploading. The export must contain every ID from `letters.csv`.

The source fetch downloads new and refreshed PDFs and attachments, compares them with
published files, and records which files need upload or conversion. Publication
then uploads the changed files, Parquet, and dataset card. The CSV catalogues stay
in this GitHub repository. Original letter PDFs live
under `letters/{year}/{rbid}.pdf`, and attachments under `attachments/{year}/{id}.{extension}`.
Source 404s and empty responses are recorded in `unavailable_files.json`;
other download failures stop publication. The Hugging Face upload helper
publishes the selected files in one call.
It may split large uploads into multiple commits.

Legacy DOC and XLS attachments are also converted with LibreOffice to
`attachments/{year}/{id}.docx` and `attachments/{year}/{id}.xlsx`. Both the original and the
converted file are published. Downstream importers can use the OOXML version
without running their own conversion. Install `libreoffice-writer` and
`libreoffice-calc` before converting locally if the source fetch identifies files
that need conversion. The workflow installs them only when needed. Published
conversions are reused when the original attachment is unchanged.

The nightly GitHub Action refreshes existing letters decided since the start of
the previous calendar year, new IDs, and the last 100 missing IDs. On Sundays it
rechecks every missing ID in that period, then publishes to Hugging Face.
`letters.csv` includes `expenditure_areas` as semicolon-separated numeric UO codes;
the Parquet column stores a list of integers. Both come from Statsliggaren's annual
expenditure-area lists. A letter may belong to several areas. Amendment decisions
may be dated one year after the budget period in which they are listed, so the
refresh also reads the preceding year's area lists and retains existing area
values when a refreshed list does not contain the letter.
To refresh an older period manually, run `uv run -m run --refresh-since 2020-01-01`
before building/uploading the export. Refreshing a letter replaces its metadata,
attachment listing and local HTML/XHTML/Markdown instead of appending duplicate rows.
Add `--scan-all-gaps` when a manual run should also recheck every missing ID in
the period.

Configure:

- `HF_DATASET_REPO_ID` as a GitHub Actions variable (the existing secret is also supported)
- `HF_TOKEN` as a GitHub Actions secret

Missing publication configuration fails the job instead of silently skipping uploads.
The Parquet path is `letters.parquet` at the dataset root.

## License

License for the data is CC0, as the files are public documents (*offentliga handlingar*).
License for the code is AGPLv3.
