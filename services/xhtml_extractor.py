from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag

from services.template_classifier import TemplateVariant


@dataclass
class ExtractedLetter:
    header_fragment: str | None = None
    body_fragment: str | None = None
    footer_fragment: str | None = None
    header_lines: list[str] = field(default_factory=list)


class XHTMLExtractor(object):
    CLASSIC_VARIANTS = {
        TemplateVariant.CLASSIC_BREVHUVUD,
        TemplateVariant.LEGACY_R_VILLKOR,
        TemplateVariant.SECTIONED_EARLY,
        TemplateVariant.SECTIONED_MODERN,
    }

    WORD_VARIANTS = {
        TemplateVariant.WORD_BLOCKBASE,
        TemplateVariant.WORD_DOCUMENTHEAD,
    }

    FRAGMENT_SELECTORS = {
        TemplateVariant.CLASSIC_BREVHUVUD: {
            "header": "#BrevHuvud",
            "body": "#RegleringsbrevBody",
            "footer": "#Dokumentfot",
        },
        TemplateVariant.LEGACY_R_VILLKOR: {
            "header": "#BrevHuvud",
            "body": "#RegleringsbrevBody",
            "footer": "#Dokumentfot",
        },
        TemplateVariant.SECTIONED_EARLY: {
            "header": "#BrevHuvud",
            "body": "#RegleringsbrevBody",
            "footer": "#Dokumentfot",
        },
        TemplateVariant.SECTIONED_MODERN: {
            "header": "#BrevHuvud",
            "body": "#RegleringsbrevBody",
            "footer": "#Dokumentfot",
        },
        TemplateVariant.WORD_BLOCKBASE: {
            "body": ".documentBody, .section3",
        },
        TemplateVariant.WORD_DOCUMENTHEAD: {
            "body": ".documentBody, .section3",
        },
    }

    @staticmethod
    def extract(
        source: BeautifulSoup,
        variant: TemplateVariant,
        clean_text,
        strings_from_tag,
        strings_from_selector,
    ) -> ExtractedLetter:
        if variant in XHTMLExtractor.CLASSIC_VARIANTS:
            selectors = XHTMLExtractor.FRAGMENT_SELECTORS[variant]
            return ExtractedLetter(
                header_fragment=XHTMLExtractor._tag_html(
                    XHTMLExtractor._select_first(source, selectors["header"])
                ),
                body_fragment=XHTMLExtractor._tag_html(
                    XHTMLExtractor._select_first(source, selectors["body"])
                ),
                footer_fragment=XHTMLExtractor._tag_html(
                    XHTMLExtractor._select_first(source, selectors["footer"])
                ),
            )

        if variant in XHTMLExtractor.WORD_VARIANTS:
            body_selector = XHTMLExtractor.FRAGMENT_SELECTORS[variant]["body"]
            header_root = source.select_one(".documentHead") or source.select_one(
                ".section1"
            )
            return ExtractedLetter(
                header_lines=strings_from_tag(header_root),
                body_fragment=XHTMLExtractor._tag_html(
                    XHTMLExtractor._select_first(source, body_selector)
                ),
            )

        if variant == TemplateVariant.LEGACY_TABLE:
            return ExtractedLetter(
                header_lines=XHTMLExtractor._legacy_table_header_lines(
                    source, clean_text, strings_from_selector
                ),
                body_fragment=XHTMLExtractor._legacy_table_body_fragment(source),
            )

        return ExtractedLetter()

    @staticmethod
    def _legacy_table_header_lines(source: BeautifulSoup, clean_text, strings_from_selector) -> list[str]:
        lines = []
        lines.extend(strings_from_selector(source, ".departement"))
        lines.extend(strings_from_selector(source, ".beslut"))
        lines.extend(strings_from_selector(source, ".datum"))
        lines.extend(strings_from_selector(source, ".diarie"))

        for tag in source.select("table.invisible td.adress"):
            text = clean_text(tag.get_text(" ", strip=True))
            if text:
                lines.append(text)

        return lines

    @staticmethod
    def _legacy_table_body_fragment(source: BeautifulSoup) -> str | None:
        start = source.select_one("div[sektion='inledning']")
        if not start or not start.parent:
            return None

        fragments = []
        collecting = False
        for child in start.parent.children:
            if child is start:
                collecting = True

            if not collecting or not isinstance(child, Tag):
                continue

            if child.name == "div":
                fragments.append(str(child))

        return "".join(fragments) or None

    @staticmethod
    def _tag_html(tag: Tag | None) -> str | None:
        return str(tag) if tag else None

    @staticmethod
    def _select_first(source: BeautifulSoup, selector_list: str) -> Tag | None:
        for selector in (item.strip() for item in selector_list.split(",")):
            if not selector:
                continue
            tag = source.select_one(selector)
            if tag:
                return tag
        return None
