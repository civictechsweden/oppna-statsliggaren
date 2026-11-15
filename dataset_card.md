---
license: cc0-1.0
language:
- sv
tags:
- regleringsbrev
- myndighet
- regeringen
- regeringskansliet
pretty_name: Öppna Statsliggaren
size_categories:
- 10K<n<100K
configs:
- config_name: default
  default: true
  data_files:
  - split: train
    path: letters.parquet
---

# Öppna Statsliggaren

Swedish government mission letters (*regleringsbrev*) for agencies and
appropriations, including amendment decisions, from
[Statsliggaren](https://www.statskontoret.se/statsliggaren/).

The [Öppna Statsliggaren scraper](https://github.com/civictechsweden/oppna-statsliggaren)
updates this repository nightly. It discovers new IDs and revisits letters
decided since the start of the previous calendar year. Historical corrections
outside that window require an explicit backfill.

## Files

- `letters.parquet`: original letter HTML, cleaned XHTML and Markdown, plus
  `id`, `original_rbid`, `type`, `date`, `year`, `category`, `name`, `department`,
  `expenditure_areas`, `registry_numbers` and `pdf`.
- `letters/{year}/{rbid}.pdf`: available original letter PDFs, using the full-letter version.
- `attachments/{year}/{id}.{extension}`: original attachment files, including PDF,
  DOC, DOCX, XLS and XLSX. Stored filenames use the numeric attachment ID.
- `attachments/{year}/{id}.docx` and `attachments/{year}/{id}.xlsx`: LibreOffice conversions
  of legacy DOC and XLS attachments, alongside the unchanged originals. The
  [GitHub attachment catalogue](https://github.com/civictechsweden/oppna-statsliggaren/blob/master/attachments.csv)
  records the original source filename.
- `unavailable_files.json`: source URLs returning 404 or empty files during the
  latest publication. These cannot be archived or converted.
- `processing_report.json`: full-corpus rebuild checks and source correction
  rules applied to individual letters.
- `organisations.json`: numbered source entries, historical names, and reviewed
  collective memberships. `organisation_ids` in Parquet is a list of integer
  references into this registry. Fetch both files at the same revision.

The department is read from the letterhead for both agency and appropriation
letters. Historical names are preserved. A department and appropriation number
are not necessarily unique identifiers; use the source IDs.

Ordinary agency letters carry their Statsliggaren organisation-entry ID.
Collective university and county-board letters carry the applicable individual
IDs, selected using the original budget year. County boards and three historical
parliamentary bodies have explicitly marked local IDs. Historical names on
letters remain unchanged; the registry retains older spellings alongside a
display name. Name-observation ranges are distinct from researched membership
periods. Appropriation letters currently have an empty recipient-ID list.
The [acquisition and collective-membership method](https://github.com/civictechsweden/oppna-statsliggaren/blob/master/docs/organisations.md)
documents sources, exceptions, and maintenance.

`original_rbid` is the RBID of the first version of the letter. Every amendment
decision carries the same value, so versions can be grouped without relying on
their names or expenditure areas. It comes from the UO lists or, when absent from
those lists, the letter page's version navigation. The value is null when the
source links do not identify a matching original letter. It reflects the source's
links, which can be wrong even when the same link appears on multiple list pages.

`registry_numbers` contains individual registry numbers expanded from the
letterhead's comma-separated shorthand. It is a string list in Parquet. Omitted
unit codes stay unknown unless independently documented.
Notes such as "Se bilaga 1" are omitted. An empty list means no readable number
was found in the letterhead, not that the decision has no registry number.

The [GitHub letter catalogue](https://github.com/civictechsweden/oppna-statsliggaren/blob/master/letters.csv)
contains the same metadata in CSV form.

The HTML column contains the letter itself, without website navigation. XHTML
normalizes the source layouts; Markdown is a lossy representation. The source
files remain available for inspection. Not every letter has a PDF; unavailable
source downloads are reported in the publishing workflow logs.

XHTML and Markdown retain local headings, with heading roles aligned across
letter generations. Deep headings are capped at h6. Explicit source repairs and
the alignment policy are maintained separately in the
[parser source](https://github.com/civictechsweden/oppna-statsliggaren/tree/master/services).
The original HTML is preserved. XHTML retains row and column spans; Markdown
tables do not retain their geometry. Prefer XHTML when importing into Docling.

The Parquet split includes letters only. PDF and attachment folders are supporting
files and are not additional dataset splits. The GitHub CSV catalogues and this
Parquet export are refreshed in the same publishing workflow.

## Read selected columns

```python
import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download

path = hf_hub_download(
    repo_id="PierreMesure/oppna-statsliggaren",
    repo_type="dataset",
    filename="letters.parquet",
)
table = pq.read_table(path, columns=["id", "department", "md"])
```
