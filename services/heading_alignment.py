"""Align heading roles across letter templates without removing boundaries.

These are interpretation rules, not corrections to the original source text.
Finance uses a compact hierarchy: UO h4, appropriation h5, post h6. The
allocation subsection is a peer of UO, leaving room for the appropriation and
post in Markdown's six levels. Deeper policy labels stay at h6 rather than
disappearing, although Markdown cannot retain a seventh ancestor.
"""

import re

from selectolax.lexbor import LexborNode

from services import html_dom as dom


MAJOR_DIVISIONS = {
    "verksamhet", "finansiering", "avgifter och bidrag", "övriga bestämmelser",
    "undantag från ekonomiadministrativa regelverket", "undantag från ea-regler",
}
MAIN_SECTIONS = {
    "verksamhetsstyrning", "mål och återrapporteringskrav",
    "övriga mål och återrapporteringskrav", "organisationsstyrning", "uppdrag",
    "anslag", "övriga villkor", "övriga intäkter",
}
POLICY_ROLES = {"politikområde": 4, "verksamhetsområde": 5, "verksamhetsgren": 6,
                "po": 4, "vo": 5, "vg": 6}
LABELS = {"mål", "återrapportering", "villkor"}
NUMBERED = re.compile(r"^(\d+(?:\.\d+)*)(\.)?\s+(.+)$")


def align_headings(document: LexborNode, clean_text) -> None:
    body = dom.find(document, "body")
    if body is None:
        return

    first = True
    section_level = 2
    section_number = None
    numbered_parent_level = 2
    topic_level = None
    policy_level = None
    in_finance = False
    in_policy_section = False

    for node in list(dom.find_all(body, recursive=False)):
        is_heading = bool(re.fullmatch(r"h[1-6]", node.tag))
        text = clean_text(dom.text(node, " ", strip=True))
        if not text:
            continue

        # Legacy role paragraphs have exact prefixes emitted by the parser.
        if not is_heading:
            role = re.match(r"^(PO|VO|VG)\s+\S", text)
            if node.tag == "p" and role and in_policy_section:
                policy_level = POLICY_ROLES[role[1].lower()]
                topic_level = None
                dom.rename(node, f"h{policy_level}")
            continue

        if first:
            node = dom.rename(node, "h1")
            dom.set_attr(node, "class", "document-title")
            first = False
            continue

        match = NUMBERED.match(text)
        title = match[3] if match else text
        key = title.casefold()

        if key in MAJOR_DIVISIONS:
            level = 2
            section_level = numbered_parent_level = 2
            section_number = match[1] if match else None
            topic_level = policy_level = None
            in_finance = key in {"finansiering", "avgifter och bidrag"}
            in_policy_section = False
        elif key in MAIN_SECTIONS:
            level = 3
            section_level = level
            numbered_parent_level = level
            section_number = match[1] if match else None
            topic_level = policy_level = None
            in_policy_section = key in {
                "verksamhetsstyrning", "mål och återrapporteringskrav",
                "övriga mål och återrapporteringskrav",
            }
        elif key == "kopia till" or re.match(r"^(bilaga \d+ till|diarienummerförteckning)", key):
            level = 2
            section_level, section_number = 2, None
            topic_level = policy_level = None
            in_policy_section = False
        elif re.match(r"^utgiftsområde\s+\d+", key):
            level = 4
            topic_level, policy_level = level, None
        elif re.match(r"^\d+:\d+\s+ap\.\s*\d+", text):
            level = 6
            topic_level = level
        elif re.match(r"^\d+:\d+\s", text):
            level = 5
            topic_level = level
        elif re.match(r"^ap\.\s*\d+", key):
            level = 6
            topic_level = level
        elif key.startswith("villkor för anslag "):
            level = 5
            topic_level = level
        elif any(key.startswith(role + " ") for role in POLICY_ROLES):
            role = key.split()[0]
            level = POLICY_ROLES[role]
            policy_level = level
            topic_level = None
        elif key in LABELS or re.match(r"^mål(?: \d+| för | - )", key):
            level = min(6, (policy_level or topic_level or section_level) + 1)
        elif match and not match[2]:
            number = match[1]
            if section_number and number.startswith(section_number + "."):
                level = min(6, numbered_parent_level + len(number.split(".")) - len(section_number.split(".")))
            elif section_number and len(number.split(".")) == len(section_number.split(".")):
                level = numbered_parent_level
                section_number = number
            else:
                level = min(6, len(number.split(".")) + 2)
            section_level = level
            topic_level = policy_level = None
        else:
            level = min(6, section_level + 1)
            topic_level = level
            # Finance captions are local to their subsection, not new roots.
            if in_finance:
                policy_level = None

        dom.rename(node, f"h{level}")
