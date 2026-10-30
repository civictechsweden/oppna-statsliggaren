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
  `id`, `type`, `date`, `year`, `category`, `name`, `department` and `pdf`.
- `letters.csv`: letter catalogue using `rbid` for the same source ID.
- `attachments.csv`: attachment catalogue with `id`, `rbid` and source filename.
- `letters/{year}/{rbid}.pdf`: available original letter PDFs, using the full-letter version.
- `attachments/{year}/{id}.{extension}`: original attachment files, including PDF,
  DOC, DOCX, XLS and XLSX. Formats and source filenames are preserved in the
  attachment catalogue; stored filenames use the numeric attachment ID.
- `attachments/{year}/{id}.docx` and `attachments/{year}/{id}.xlsx`: LibreOffice conversions
  of legacy DOC and XLS attachments, alongside the unchanged originals. The
  source filename in `attachments.csv` distinguishes originals from derivatives.
- `unavailable_files.json`: source URLs returning 404 or empty files during the
  latest publication. These cannot be archived or converted.

The department is read from the letterhead for both agency and appropriation
letters. Historical names are preserved. A department and appropriation number
are not necessarily unique identifiers; use the source IDs.

The HTML column contains the letter itself, without website navigation. XHTML
normalizes the source layouts; Markdown is a lossy representation. The source
files remain available for inspection. Not every letter has a PDF; unavailable
source downloads are reported in the publishing workflow logs.

The Parquet split includes letters only. PDF and attachment folders are supporting
files and are not additional dataset splits. File uploads precede the catalogue
commit; an interrupted run can leave additional files pending the next catalogue
update. Each catalogue publication contains matching CSV and Parquet metadata.

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
