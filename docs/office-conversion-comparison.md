# Legacy Office conversion comparison

Tested on 2026-10-30 with office-oxide 0.1.16 and LibreOffice 26.8.2.2,
using CPython 3.14.2 on macOS arm64. All six samples converted and produced
readable OOXML containers with both converters. **The replacement is not
fidelity-equivalent: spreadsheet formulas are lost and Word layouts change.**

## Samples and results

The sample uses the first, middle and last unique attachment IDs in each legacy
format in the local catalogue. Originals were downloaded from
[the published dataset](https://huggingface.co/datasets/PierreMesure/oppna-statsliggaren/tree/18245e27ff5c3e508300e94ec39026dc5e85df85)
at revision `18245e27ff5c3e508300e94ec39026dc5e85df85`. This is a small
compatibility check, not a representative benchmark of the whole archive.

| Original path | Catalogue name | Result with office-oxide compared with LibreOffice |
| --- | --- | --- |
| `attachments/2003/77.doc` | prognosmall03.doc | All 3 tables, 7 rows and 48 cells retained. Body words match after joining soft-hyphen word breaks. Both footnotes retained, with extra literal `footnote` text in the office-oxide XML. Both render as 1 page. |
| `attachments/2008/2310.doc` | Bilaga 2 – Lunds universitet.doc | Body words match exactly; all 11 tables, 66 rows and 201 cells retained. Header text retained; footer/page numbering differs. Original renders as 7 pages, office-oxide output as 6. |
| `attachments/2026/11057.doc` | Verksamhetsinvesteringsbudget.doc | Body words and header match; all 1 table, 15 rows and 105 cells retained. Original landscape page becomes 2 portrait pages. Visual inspection shows the label column squeezed into excessive wrapping. |
| `attachments/2003/123.xls` | Bilaga-9 4 dec.xls | All 188 populated source cells retain their displayed information, but date cell `R6` in `13.6 FoT` becomes the string `2003-04-01` instead of a typed date. All 19 formulas are replaced by cached values. All 50 merged ranges retained. |
| `attachments/2008/2667.xls` | Bilaga 44 – Anvisningar redovisning av högskoleutb.xls | All 156 populated source cells retain their values. All 33 formulas are replaced by cached values. Merged ranges decrease from 3 to 2. |
| `attachments/2017/5633.xls` | Bilaga 1.xls | All 48 populated source cells and all 3 sheet names retained. Source has no formulas or merged ranges. |

LibreOffice preserved all 52 formulas, the typed date, all 53 merged ranges and
all populated source-cell values across the three spreadsheets. Both converters
preserved the seven worksheet names in their original order. Cached formula
values matched the originals in the office-oxide XLSX files, but editing input
cells will no longer recalculate those results.

Word text was compared as Unicode word tokens from `word/document.xml`.
Header/footer and footnote text was inspected separately. Table, row and cell
counts came from the corresponding OOXML elements. Retaining these elements
does not imply retaining layout, styles or dynamic fields. The original DOCs
and office-oxide DOCX files were rendered to PDF by the same LibreOffice binary
with separate temporary profiles; page counts came from LiteParse. The original
and converted investment-budget pages were also visually inspected.

Spreadsheet source values, date types, worksheet order and merged ranges were
read with xlrd 2.0.2. Formula counts were independently counted from the source
BIFF `FORMULA` records using olefile 0.47. Both XLSX outputs were read with
openpyxl 3.1.5, once with cached values and once with formula expressions.
No comparison libraries are added to the application dependencies.

## Weight and timing

The pinned office-oxide package has no runtime dependencies. Its Linux x86-64
wheel is 2,453,123 bytes, and a binary-only resolution for Python 3.14 on the
Ubuntu runner platform succeeds. The workflow can therefore remove its
`apt-get update` and LibreOffice Writer/Calc installation step.

The initial six office-oxide calls took approximately 1.3–3.6 ms per file,
including opening and saving the document. These are local single-run timings;
they do not measure GitHub Actions startup, installation, or overall workflow
speed. Output files were 3,983–8,639 bytes, versus 8,458–41,499 bytes from
LibreOffice. Some of that reduction corresponds to information loss.

## Repeating the conversion

Download the exact originals with the Hugging Face CLI:

```sh
hf download PierreMesure/oppna-statsliggaren \
  attachments/2003/77.doc attachments/2008/2310.doc attachments/2026/11057.doc \
  attachments/2003/123.xls attachments/2008/2667.xls attachments/2017/5633.xls \
  --repo-type dataset --revision 18245e27ff5c3e508300e94ec39026dc5e85df85 \
  --local-dir /tmp/statsliggaren-office-source
```

On this branch, run the actual publication converter without uploading anything:

```sh
uv sync --frozen
uv run python - <<'PY'
from pathlib import Path
from services.artifacts import convert_attachments

root = Path('/tmp/statsliggaren-office-source')
paths = sorted(str(p.relative_to(root)) for p in root.glob('attachments/*/*')
               if p.suffix in ('.doc', '.xls'))
print(convert_attachments(root, paths))
PY
```

For the LibreOffice baseline, convert the same originals to separate output
directories, using `--headless --convert-to docx` for DOC and
`--headless --convert-to xlsx` for XLS. Give each process a separate profile
with `-env:UserInstallation=file:///tmp/unique-office-profile`. Use a separate
output directory for PDF rendering as well.

The six samples also passed the new production conversion function. SHA-256
checks confirmed that all originals were unchanged. Running the function again
reused all derivatives without changing their modification times. The full
unit suite passed (52 tests), including derivative validation, failure
preservation and cache reuse.

## Merge consideration

This change is suitable only if published OOXML files are intended as content
derivatives and consumers can return to the originals for formulas, types and
layout. The [upstream conversion documentation](https://office.oxide.fyi/rust/docs/conversion/legacy-to-ooxml)
also describes cached-value-only XLS conversion. Keeping the PR in draft makes
the observed regressions explicit before adopting this tradeoff.
