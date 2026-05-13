from dataclasses import dataclass, field
import re

from bs4 import BeautifulSoup, Tag

from services.template_classifier import TemplateVariant


@dataclass
class ExtractedLetter:
    header_fragment: str | None = None
    body_fragment: str | None = None
    footer_fragment: str | None = None
    header_lines: list[str] = field(default_factory=list)


class XHTMLExtractor(object):
    LETTERHEAD_TABLE_CLASS = "letterhead"
    DOCUMENT_TITLE_CLASS = "document-title"
    LETTERHEAD_CELL_CLASSES = {
        "department": "letterhead-department",
        "decision": "letterhead-decision",
        "decision_number": "letterhead-decision-number",
        "date": "letterhead-date",
        "diary": "letterhead-diary",
        "recipient": "letterhead-recipient",
    }

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
            body_tag = XHTMLExtractor._select_first(source, selectors["body"])
            footer_tag = XHTMLExtractor._select_first(source, selectors["footer"])
            return ExtractedLetter(
                header_fragment=XHTMLExtractor._classic_header_fragment(
                    source, clean_text
                ),
                body_fragment=XHTMLExtractor._tag_html(
                    XHTMLExtractor._body_without_footer(body_tag, selectors["footer"])
                ),
                footer_fragment=XHTMLExtractor._tag_html(footer_tag),
            )

        if variant in XHTMLExtractor.WORD_VARIANTS:
            body_selector = XHTMLExtractor.FRAGMENT_SELECTORS[variant]["body"]
            header_root = source.select_one(".documentHead") or source.select_one(
                ".section1"
            )
            return ExtractedLetter(
                header_fragment=XHTMLExtractor._word_header_fragment(
                    header_root, clean_text, strings_from_tag
                ),
                body_fragment=XHTMLExtractor._tag_html(
                    XHTMLExtractor._select_first(source, body_selector)
                ),
            )

        if variant == TemplateVariant.LEGACY_TABLE:
            return ExtractedLetter(
                header_fragment=XHTMLExtractor._legacy_table_header_fragment(
                    source, clean_text
                ),
                body_fragment=XHTMLExtractor._legacy_table_body_fragment(source),
            )

        return ExtractedLetter()

    @staticmethod
    def _legacy_table_header_fragment(source: BeautifulSoup, clean_text) -> str | None:
        department = source.select_one(".departement")
        department_text = clean_text(department.get_text(" ", strip=True)) if department else ""
        decision_cells = source.select("td.info")
        left_decision = ""
        right_decision = ""
        if decision_cells:
            left_decision = clean_text(decision_cells[0].get_text(" ", strip=True))
        if len(decision_cells) > 1:
            right_decision = clean_text(decision_cells[1].get_text(" ", strip=True))

        date_tag = source.select_one(".datum")
        date_text = clean_text(date_tag.get_text(" ", strip=True)) if date_tag else ""

        diary = source.select_one(".diarie")
        diary_lines = []
        if diary:
            for item in diary.stripped_strings:
                text = clean_text(item)
                if text:
                    diary_lines.append(text)

        address_lines = []
        for tag in source.select("table.invisible td.adress"):
            text = clean_text(tag.get_text(" ", strip=True))
            if text:
                address_lines.append(text)

        return XHTMLExtractor._build_letterhead_table(
            [
                ("department", [department_text], None, []),
                ("decision", [left_decision], "decision_number", [right_decision]),
                ("date", [date_text], "diary", diary_lines),
                (None, [], "recipient", address_lines),
            ]
        )

    @staticmethod
    def _classic_header_fragment(source: BeautifulSoup, clean_text) -> str | None:
        department = source.select_one("#RubrikSektion .avs, #BrevHuvud .avs")
        decision = source.select_one("#BeslutTyp")
        decision_number = source.select_one("#BeslutNr")
        date = source.select_one("#BeslutDatum")
        diary = source.select_one("#DiarieNr")
        recipient = source.select_one("#AdressSektion")

        return XHTMLExtractor._build_letterhead_table(
            [
                (
                    "department",
                    XHTMLExtractor._cleaned_lines_from_tag(department, clean_text),
                    None,
                    [],
                ),
                (
                    "decision",
                    XHTMLExtractor._cleaned_lines_from_tag(decision, clean_text),
                    "decision_number",
                    XHTMLExtractor._cleaned_lines_from_tag(decision_number, clean_text),
                ),
                (
                    "date",
                    XHTMLExtractor._cleaned_lines_from_tag(date, clean_text),
                    "diary",
                    XHTMLExtractor._cleaned_lines_from_tag(diary, clean_text),
                ),
                (
                    None,
                    [],
                    "recipient",
                    XHTMLExtractor._cleaned_lines_from_tag(recipient, clean_text),
                ),
            ]
        )

    @staticmethod
    def _word_header_fragment(header_root: Tag | None, clean_text, strings_from_tag) -> str | None:
        if not header_root:
            return None

        lines = [clean_text(text) for text in strings_from_tag(header_root) if clean_text(text)]
        if not lines:
            return None

        department = lines[0] if len(lines) > 0 else ""
        decision = lines[1] if len(lines) > 1 else ""
        decision_number = lines[2] if len(lines) > 2 else ""

        date_index = None
        for index, line in enumerate(lines[3:], start=3):
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", line):
                date_index = index
                break
        date_text = lines[date_index] if date_index is not None else ""

        trailing = lines[date_index + 1 :] if date_index is not None else lines[3:]
        diary_lines = []
        while trailing and XHTMLExtractor._looks_like_diary_line(trailing[-1]):
            diary_lines.insert(0, trailing.pop())
        address_lines = trailing

        return XHTMLExtractor._build_letterhead_table(
            [
                ("department", [department], None, []),
                ("decision", [decision], "decision_number", [decision_number]),
                ("date", [date_text], "diary", diary_lines),
                (None, [], "recipient", address_lines),
            ]
        )

    @staticmethod
    def _build_letterhead_table(
        rows: list[tuple[str | None, list[str], str | None, list[str]]]
    ) -> str | None:
        document = BeautifulSoup("", "html.parser")
        table = document.new_tag("table")
        table["class"] = [XHTMLExtractor.LETTERHEAD_TABLE_CLASS]

        has_content = False
        for left_role, left_lines, right_role, right_lines in rows:
            left_lines = [line for line in left_lines if line]
            right_lines = [line for line in right_lines if line]
            if not left_lines and not right_lines:
                continue

            has_content = True
            tr = document.new_tag("tr")
            if left_lines:
                tr.append(
                    XHTMLExtractor._build_letterhead_cell(
                        document,
                        left_role,
                        left_lines,
                    )
                )
            if right_lines:
                tr.append(
                    XHTMLExtractor._build_letterhead_cell(
                        document,
                        right_role,
                        right_lines,
                    )
                )
            table.append(tr)

        return str(table) if has_content else None

    @staticmethod
    def _build_letterhead_cell(
        document: BeautifulSoup, role: str | None, lines: list[str]
    ) -> Tag:
        td = document.new_tag("td")
        if role:
            td["class"] = [XHTMLExtractor.LETTERHEAD_CELL_CLASSES[role]]
        for index, line in enumerate(lines):
            if index:
                td.append(document.new_tag("br"))
            td.append(line)
        return td

    @staticmethod
    def _cleaned_lines_from_tag(tag: Tag | None, clean_text) -> list[str]:
        if not tag:
            return []
        return [clean_text(text) for text in tag.stripped_strings if clean_text(text)]

    @staticmethod
    def _looks_like_diary_line(text: str) -> bool:
        return bool(re.match(r"^[A-Za-zÅÄÖåäö]{1,4}\d{4}/\d+", text))

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
    def _body_without_footer(body_tag: Tag | None, footer_selector: str) -> Tag | None:
        if not body_tag:
            return None

        body_copy = BeautifulSoup(str(body_tag), "html.parser").find(True)
        if not body_copy:
            return None

        for selector in (item.strip() for item in footer_selector.split(",")):
            if not selector:
                continue
            footer = body_copy.select_one(selector)
            if footer:
                footer.decompose()

        return body_copy

    @staticmethod
    def _select_first(source: BeautifulSoup, selector_list: str) -> Tag | None:
        for selector in (item.strip() for item in selector_list.split(",")):
            if not selector:
                continue
            tag = source.select_one(selector)
            if tag:
                return tag
        return None
