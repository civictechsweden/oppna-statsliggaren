import re
from dataclasses import dataclass, field

from selectolax.lexbor import LexborNode

from services import html_dom as dom
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
        source: LexborNode,
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
            header_root = dom.select_one(source, ".documentHead") or dom.select_one(
                source, ".section1"
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
    def _legacy_table_header_fragment(source: LexborNode, clean_text) -> str | None:
        department = dom.select_one(source, ".departement")
        department_text = (
            clean_text(dom.text(department, " ", strip=True)) if department else ""
        )
        decision_cells = dom.select(source, "td.info")
        left_decision = ""
        right_decision = ""
        if decision_cells:
            left_decision = clean_text(dom.text(decision_cells[0], " ", strip=True))
        if len(decision_cells) > 1:
            right_decision = clean_text(dom.text(decision_cells[1], " ", strip=True))

        date_tag = dom.select_one(source, ".datum")
        date_text = clean_text(dom.text(date_tag, " ", strip=True)) if date_tag else ""

        diary = dom.select_one(source, ".diarie")
        diary_lines = []
        if diary:
            for item in dom.strings(diary):
                text = clean_text(item)
                if text:
                    diary_lines.append(text)

        address_lines = []
        for tag in dom.select(source, "table.invisible td.adress"):
            text = clean_text(dom.text(tag, " ", strip=True))
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
    def _classic_header_fragment(source: LexborNode, clean_text) -> str | None:
        department = dom.select_one(source, "#RubrikSektion .avs, #BrevHuvud .avs")
        decision = dom.select_one(source, "#BeslutTyp")
        decision_number = dom.select_one(source, "#BeslutNr")
        date = dom.select_one(source, "#BeslutDatum")
        diary = dom.select_one(source, "#DiarieNr")
        recipient = dom.select_one(source, "#AdressSektion")

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
    def _word_header_fragment(
        header_root: LexborNode | None, clean_text, strings_from_tag
    ) -> str | None:
        if not header_root:
            return None

        lines = [
            clean_text(text)
            for text in strings_from_tag(header_root)
            if clean_text(text)
        ]
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
        rows: list[tuple[str | None, list[str], str | None, list[str]]],
    ) -> str | None:
        document = dom.parse_html("")
        table = document.parser.create_node("table")
        dom.set_attr(table, "class", [XHTMLExtractor.LETTERHEAD_TABLE_CLASS])

        has_content = False
        for left_role, left_lines, right_role, right_lines in rows:
            left_lines = [line for line in left_lines if line]
            right_lines = [line for line in right_lines if line]
            if not left_lines and not right_lines:
                continue

            has_content = True
            tr = document.parser.create_node("tr")
            tr.insert_child(
                XHTMLExtractor._build_letterhead_cell(
                    document, left_role if left_lines else None, left_lines
                )
            )
            tr.insert_child(
                XHTMLExtractor._build_letterhead_cell(
                    document, right_role if right_lines else None, right_lines
                )
            )
            table.insert_child(tr)

        return dom.markup(table) if has_content else None

    @staticmethod
    def _build_letterhead_cell(
        document: LexborNode, role: str | None, lines: list[str]
    ) -> LexborNode:
        td = document.parser.create_node("td")
        if role:
            dom.set_attr(td, "class", [XHTMLExtractor.LETTERHEAD_CELL_CLASSES[role]])
        for index, line in enumerate(lines):
            if index:
                td.insert_child(document.parser.create_node("br"))
            td.insert_child(line)
        return td

    @staticmethod
    def _cleaned_lines_from_tag(tag: LexborNode | None, clean_text) -> list[str]:
        if not tag:
            return []
        return [clean_text(text) for text in dom.strings(tag) if clean_text(text)]

    @staticmethod
    def _looks_like_diary_line(text: str) -> bool:
        return bool(re.match(r"^[A-Za-zÅÄÖåäö]{1,4}\d{4}/\d+", text))

    @staticmethod
    def _legacy_table_body_fragment(source: LexborNode) -> str | None:
        start = dom.select_one(source, "div[sektion='inledning']")
        if not start or not start.parent:
            return None

        fragments = []
        collecting = False
        for child in dom.children(start.parent):
            if child == start:
                collecting = True

            if not collecting or not dom.is_tag(child):
                continue

            if child.tag == "div":
                fragments.append(dom.markup(child))

        return "".join(fragments) or None

    @staticmethod
    def _tag_html(tag: LexborNode | None) -> str | None:
        return dom.markup(tag) if tag else None

    @staticmethod
    def _body_without_footer(
        body_tag: LexborNode | None, footer_selector: str
    ) -> LexborNode | None:
        if not body_tag:
            return None

        body_copy = dom.find(dom.parse_fragment(dom.markup(body_tag)), True)
        if not body_copy:
            return None

        for selector in (item.strip() for item in footer_selector.split(",")):
            if not selector:
                continue
            footer = dom.select_one(body_copy, selector)
            if footer:
                footer.decompose()

        return body_copy

    @staticmethod
    def _select_first(source: LexborNode, selector_list: str) -> LexborNode | None:
        for selector in (item.strip() for item in selector_list.split(",")):
            if not selector:
                continue
            tag = dom.select_one(source, selector)
            if tag:
                return tag
        return None
