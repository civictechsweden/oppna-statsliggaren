"""Source repairs and markup compatibility; original HTML stays in the export.

This ledger describes actual source errors. Cross-template heading alignment
belongs in heading_alignment, not here. IDs are also written to rebuild audits.
"""

import re


CORRECTIONS = {
    "empty-emphasis": "XHTML/HTML compatibility: close self-closing em/strong tags before HTML5 parsing; confirmed in RBID 24741.",
    "invalid-xml-characters": "Remove XML-forbidden control characters; confirmed in RBID 6180.",
    "duplicated-title-introduction": "Remove an introduction embedded in the title only when the identical introduction exists separately; RBIDs 21417 and 22697.",
    "reporting-heading-spelling": "Correct the misspelled heading Återrrapportering, retaining its content and heading level.",
    "metadata-category": "Restore omitted Myndighet/Anslag in six exact source titles: RBIDs 3174, 3290, 6079, 6878, 6879, 7747.",
    "metadata-appropriation-label": "Normalize the source catalogue category Avseende anslaget to Anslag.",
}

TITLE_REPLACEMENTS = (
    ("Ändringsbeslut 2003-09-04 Lunds universitet", "Ändringsbeslut 2003-09-04 Myndighet Lunds universitet"),
    ("2003 Avvecklingsmyndigheten för RRV", "2003 Myndighet Avvecklingsmyndigheten för RRV"),
    ("Ändringsbeslut 2003-11-27 Polisväsendet", "Ändringsbeslut 2003-11-27 Myndighet Polisväsendet"),
    ("Ändringsbeslut 2004-11-30 Regeringskansliet", "Ändringsbeslut 2004-11-30 Myndighet Regeringskansliet"),
    ("Ändringsbeslut 2004-01-29 Ändring avseende A:014 samt B:019 FI", "Ändringsbeslut 2004-01-29 Anslag A:014 samt B:019 FI"),
    ("Ändringsbeslut 2004-01-29 Ändring avseende A:005 M", "Ändringsbeslut 2004-01-29 Anslag A:005 M"),
)


def _record(applied, rule):
    if applied is not None and rule not in applied:
        applied.append(rule)


def correct_markup(html: str, applied: list[str] | None = None) -> str:
    corrected = re.sub(
        r"<(em|strong)\b([^<>]*?)/\s*>", r"<\1\2></\1>", html,
        flags=re.IGNORECASE,
    )
    if corrected != html:
        _record(applied, "empty-emphasis")
    result = re.sub(
        r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]", "", corrected
    )
    if result != corrected:
        _record(applied, "invalid-xml-characters")
    return result


def correct_document(source, applied: list[str] | None = None) -> None:
    # Imported locally because html_dom also uses the markup repair.
    from services import html_dom as dom

    title = dom.select_one(source, "#BrevInledandeText_Rubrik")
    intro = dom.select_one(source, "#BrevInledandeText_InledandeText")
    if title is not None and intro is not None:
        title_text = dom.text(title, " ", strip=True)
        intro_text = dom.text(intro, " ", strip=True)
        if (intro_text.startswith("Regeringen beslutar att följande")
                and title_text.startswith(("Regleringsbrev för", "Ändring av regleringsbrev"))
                and title_text.endswith(intro_text)):
            remaining = title_text[:-len(intro_text)].strip()
            if remaining:
                dom.set_text(title, remaining)
                _record(applied, "duplicated-title-introduction")

    correct_heading_labels(source, applied)


def correct_heading_labels(source, applied: list[str] | None = None) -> None:
    from services import html_dom as dom

    for heading in dom.find_all(source, re.compile(r"^h[1-6]$")):
        for node in dom.descendants(heading):
            if node.is_text_node and "Återrrapportering" in node.text():
                node.replace_with(node.text().replace("Återrrapportering", "Återrapportering"))
                _record(applied, "reporting-heading-spelling")


def correct_metadata_title(text: str, applied: list[str] | None = None) -> str:
    text = " ".join(text.split())
    result = text.replace("Avseende anslaget", "Anslag")
    if result != text:
        _record(applied, "metadata-appropriation-label")
    for before, after in TITLE_REPLACEMENTS:
        corrected = result.replace(before, after)
        if corrected != result:
            _record(applied, "metadata-category")
        result = corrected
    return result
