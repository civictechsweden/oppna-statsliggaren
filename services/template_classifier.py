from dataclasses import dataclass
from enum import StrEnum
import re


class TemplateFamily(StrEnum):
    LEGACY = "legacy"
    CLASSIC = "classic"
    WORD = "word"
    SECTIONED = "sectioned"
    UNKNOWN = "unknown"


class TemplateVariant(StrEnum):
    LEGACY_TABLE = "legacy_table"
    LEGACY_R_VILLKOR = "legacy_r_villkor"
    CLASSIC_BREVHUVUD = "classic_brevhuvud"
    WORD_DOCUMENTHEAD = "word_documenthead"
    WORD_BLOCKBASE = "word_blockbase"
    SECTIONED_EARLY = "sectioned_early"
    SECTIONED_MODERN = "sectioned_modern"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TemplateMatch:
    family: TemplateFamily
    variant: TemplateVariant


def classify_letter_template(html: str) -> TemplateMatch:
    if 'class="universe_tbl"' in html or 'class="world_tbl"' in html:
        return TemplateMatch(
            family=TemplateFamily.LEGACY,
            variant=TemplateVariant.LEGACY_TABLE,
        )

    if "r:villkor" in html:
        return TemplateMatch(
            family=TemplateFamily.LEGACY,
            variant=TemplateVariant.LEGACY_R_VILLKOR,
        )

    has_xhtml_namespace = 'xmlns="http://www.w3.org/1999/xhtml"' in html
    has_section_comments = "delavsnitt med" in html
    has_header_div = 'class="header-div"' in html
    has_accessible_div = 'class="accessible-div"' in html
    has_semantic_table_classes = bool(re.search(r'class="[^"]*table-[^"]*"', html))

    if has_header_div or has_accessible_div or has_semantic_table_classes:
        return TemplateMatch(
            family=TemplateFamily.SECTIONED,
            variant=TemplateVariant.SECTIONED_MODERN,
        )

    if has_xhtml_namespace and has_section_comments:
        return TemplateMatch(
            family=TemplateFamily.SECTIONED,
            variant=TemplateVariant.SECTIONED_EARLY,
        )

    if 'class="documentHead"' in html or 'class="documentBody"' in html:
        return TemplateMatch(
            family=TemplateFamily.WORD,
            variant=TemplateVariant.WORD_DOCUMENTHEAD,
        )

    if 'class="blockBaseInnerTable"' in html:
        return TemplateMatch(
            family=TemplateFamily.WORD,
            variant=TemplateVariant.WORD_BLOCKBASE,
        )

    if 'id="BrevHuvud"' in html:
        return TemplateMatch(
            family=TemplateFamily.CLASSIC,
            variant=TemplateVariant.CLASSIC_BREVHUVUD,
        )

    return TemplateMatch(
        family=TemplateFamily.UNKNOWN,
        variant=TemplateVariant.UNKNOWN,
    )
