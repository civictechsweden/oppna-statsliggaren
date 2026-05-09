import re
from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from services.template_classifier import TemplateVariant, classify_letter_template
from services.xhtml_extractor import XHTMLExtractor
from services.xhtml_outline import XHTMLOutlineNormalizer
from services.xhtml_serializer import XHTMLSerializer


class IntermediateParser(object):
    VARIANT_NORMALIZATION = {
        TemplateVariant.CLASSIC_BREVHUVUD: {
            "heading_class_pattern": None,
            "wrapper_classes": set(),
            "known_ids": True,
            "rk_rubrik": False,
        },
        TemplateVariant.LEGACY_R_VILLKOR: {
            "heading_class_pattern": None,
            "wrapper_classes": set(),
            "known_ids": True,
            "rk_rubrik": False,
        },
        TemplateVariant.SECTIONED_EARLY: {
            "heading_class_pattern": None,
            "wrapper_classes": set(),
            "known_ids": True,
            "rk_rubrik": False,
        },
        TemplateVariant.SECTIONED_MODERN: {
            "heading_class_pattern": None,
            "wrapper_classes": set(),
            "known_ids": True,
            "rk_rubrik": False,
        },
        TemplateVariant.WORD_BLOCKBASE: {
            "heading_class_pattern": r"^rubrik(\d+)$",
            "wrapper_classes": {
                "section1",
                "section2",
                "section3",
                "standardLayout",
                "blockBaseTable",
                "blockPageWidth",
            },
            "known_ids": False,
            "rk_rubrik": False,
        },
        TemplateVariant.WORD_DOCUMENTHEAD: {
            "heading_class_pattern": r"^rubrik(\d+)$",
            "wrapper_classes": {
                "section1",
                "section2",
                "section3",
                "standardLayout",
                "blockBaseTable",
                "blockPageWidth",
            },
            "known_ids": False,
            "rk_rubrik": False,
        },
        TemplateVariant.LEGACY_TABLE: {
            "heading_class_pattern": r"^rubrik_(\d+)$",
            "wrapper_classes": {
                "invisible",
                "invisible_tbl",
                "universe_tbl",
                "world_tbl",
            },
            "known_ids": False,
            "rk_rubrik": True,
        },
    }

    ALLOWED_TAGS = {
        "a",
        "body",
        "br",
        "em",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "html",
        "li",
        "ol",
        "p",
        "strong",
        "table",
        "tbody",
        "td",
        "th",
        "thead",
        "tr",
        "ul",
    }

    BLOCK_TAGS = {
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "ol",
        "p",
        "table",
        "ul",
    }

    @staticmethod
    def parse_letter_html(html: str) -> str:
        variant = classify_letter_template(html).variant
        source = BeautifulSoup(html, "html.parser")
        document = BeautifulSoup("<html><body></body></html>", "html.parser")
        body = document.body

        extracted = XHTMLExtractor.extract(
            source,
            variant,
            IntermediateParser._clean_text,
            IntermediateParser._strings_from_tag,
            IntermediateParser._strings_from_selector,
        )
        IntermediateParser._append_extracted_content(body, extracted, variant)

        IntermediateParser._sanitize_document(document)
        IntermediateParser._normalize_anslag_summary_tables(document)
        XHTMLOutlineNormalizer.normalize(document, IntermediateParser._clean_text)
        return XHTMLSerializer.serialize_document(document, IntermediateParser._clean_text)

    @staticmethod
    def _append_extracted_content(body: Tag, extracted, variant: TemplateVariant) -> None:
        if extracted.header_lines:
            IntermediateParser._append_text_lines(body, extracted.header_lines)
        if extracted.header_fragment:
            IntermediateParser._append_fragment(body, extracted.header_fragment, variant)
        if extracted.body_fragment:
            IntermediateParser._append_fragment(body, extracted.body_fragment, variant)
        if extracted.footer_fragment:
            IntermediateParser._append_fragment(body, extracted.footer_fragment, variant)

    @staticmethod
    def _append_fragment(body: Tag, fragment_html: str, variant: TemplateVariant) -> None:
        fragment = BeautifulSoup(fragment_html, "html.parser")
        IntermediateParser._normalize_fragment(fragment, variant)

        for child in list(fragment.contents):
            if isinstance(child, NavigableString):
                text = IntermediateParser._clean_text(str(child))
                if not text:
                    continue
                body.append(IntermediateParser._new_paragraph(text))
                continue

            body.append(child.extract())

    @staticmethod
    def _append_text_lines(body: Tag, lines: list[str]) -> None:
        seen = set()
        for line in lines:
            text = IntermediateParser._clean_text(line)
            if not text or text in seen:
                continue
            seen.add(text)
            body.append(IntermediateParser._new_paragraph(text))

    @staticmethod
    def _normalize_fragment(fragment: BeautifulSoup, variant: TemplateVariant) -> None:
        IntermediateParser._remove_comments(fragment)
        IntermediateParser._remove_noise(fragment)
        IntermediateParser._unwrap_tag_name(fragment, "r:villkor")
        IntermediateParser._unwrap_tag_name(fragment, "r:instruktion")
        IntermediateParser._preserve_italic_semantics(fragment)
        IntermediateParser._apply_variant_normalization(fragment, variant)

        IntermediateParser._promote_textual_blocks(fragment)

    @staticmethod
    def _apply_variant_normalization(
        fragment: BeautifulSoup, variant: TemplateVariant
    ) -> None:
        config = IntermediateParser.VARIANT_NORMALIZATION[variant]

        IntermediateParser._normalize_heading_tables(fragment)
        if config["known_ids"]:
            IntermediateParser._promote_known_ids(fragment)
        if config["heading_class_pattern"]:
            IntermediateParser._promote_classed_headings(
                fragment, pattern=config["heading_class_pattern"]
            )
        if config["rk_rubrik"]:
            for tag in fragment.select(".rkrubrik"):
                tag.name = "h1"
                tag.attrs = {}
        if config["wrapper_classes"]:
            IntermediateParser._unwrap_classed_wrappers(
                fragment,
                wrapper_classes=config["wrapper_classes"],
            )

    @staticmethod
    def _promote_known_ids(fragment: BeautifulSoup) -> None:
        heading = fragment.select_one("#BrevInledandeText_Rubrik")
        if heading:
            heading.name = "h1"
            heading.attrs = {}

        for selector in [
            "#BrevInledandeText_Bilagor",
            "#BrevInledandeText_IngressText",
            "#BrevInledandeText_InledandeText",
            "#BrevFot_Beslut",
            "#BrevFot_Minister",
            "#BrevFot_Handlaeggare",
            "#BrevFot_KopiaTillText",
        ]:
            tag = fragment.select_one(selector)
            if tag:
                tag.name = "p"
                tag.attrs = {}

    @staticmethod
    def _normalize_heading_tables(fragment: BeautifulSoup) -> None:
        for table in list(fragment.find_all("table")):
            if table.find("table"):
                continue

            rows = table.find_all("tr", recursive=False)
            if not rows and table.tbody:
                rows = table.tbody.find_all("tr", recursive=False)

            if len(rows) != 1:
                continue

            cells = rows[0].find_all(["td", "th"], recursive=False)
            if not 1 <= len(cells) <= 2:
                continue

            texts = []
            heading_levels = []
            first_text = ""

            for index, cell in enumerate(cells):
                cell_text = IntermediateParser._clean_text(cell.get_text(" ", strip=True))
                if not cell_text:
                    continue
                if index == 0:
                    first_text = cell_text
                texts.append(cell_text)

                for heading in cell.find_all(re.compile(r"^h[1-6]$")):
                    heading_levels.append(int(heading.name[1]))

                for descendant in cell.find_all(True):
                    heading_levels.extend(
                        IntermediateParser._heading_levels_from_classes(
                            descendant.get("class", [])
                        )
                    )

            if len(texts) < 2:
                continue

            if not heading_levels and not re.fullmatch(r"\d+(?:\.\d+)*", first_text):
                continue

            level = min(heading_levels) if heading_levels else min(
                6, first_text.count(".") + 2
            )

            heading = fragment.new_tag(f"h{level}")
            heading.string = " ".join(texts)
            table.replace_with(heading)

    @staticmethod
    def _promote_classed_headings(fragment: BeautifulSoup, pattern: str) -> None:
        regex = re.compile(pattern)
        for tag in list(fragment.find_all(True)):
            if tag.name in IntermediateParser.ALLOWED_TAGS:
                continue

            levels = []
            for class_name in tag.get("class", []):
                match = regex.match(class_name)
                if match:
                    levels.append(min(6, int(match.group(1))))

            if not levels:
                continue

            if tag.parent and tag.parent.name in {"td", "th"}:
                continue

            tag.name = f"h{min(levels)}"
            tag.attrs = {}

    @staticmethod
    def _heading_levels_from_classes(class_names: list[str]) -> list[int]:
        levels = []
        for class_name in class_names:
            legacy_match = re.fullmatch(r"rubrik_(\d+)", class_name)
            word_match = re.fullmatch(r"rubrik(\d+)", class_name)

            if legacy_match:
                levels.append(min(6, int(legacy_match.group(1))))
            elif word_match:
                levels.append(min(6, int(word_match.group(1))))

        return levels

    @staticmethod
    def _unwrap_classed_wrappers(
        fragment: BeautifulSoup, wrapper_classes: set[str]
    ) -> None:
        for tag in list(fragment.find_all(True)):
            if tag.name in IntermediateParser.ALLOWED_TAGS:
                continue

            classes = set(tag.get("class", []))
            if classes & wrapper_classes:
                tag.unwrap()

    @staticmethod
    def _promote_textual_blocks(fragment: BeautifulSoup) -> None:
        for tag in list(fragment.find_all(True)):
            if tag.name in IntermediateParser.ALLOWED_TAGS:
                continue

            if tag.name in {"script", "style", "img", "hr"}:
                tag.decompose()
                continue

            if tag.parent and tag.parent.name in {
                "a",
                "h1",
                "h2",
                "h3",
                "h4",
                "h5",
                "h6",
                "li",
                "p",
                "td",
                "th",
            }:
                tag.unwrap()
                continue

            has_block_child = any(
                isinstance(child, Tag)
                and child.name in IntermediateParser.BLOCK_TAGS
                for child in tag.children
            )

            text = IntermediateParser._clean_text(tag.get_text(" ", strip=True))
            if has_block_child:
                tag.unwrap()
            elif text:
                tag.name = "p"
                tag.attrs = {}
            else:
                tag.decompose()

    @staticmethod
    def _sanitize_document(document: BeautifulSoup) -> None:
        IntermediateParser._remove_comments(document)
        IntermediateParser._remove_noise(document)

        for tag in list(document.find_all(True)):
            if tag.name not in IntermediateParser.ALLOWED_TAGS:
                tag.unwrap()
                continue

            if tag.name == "a":
                href = tag.get("href")
                tag.attrs = {"href": href} if href else {}
            elif tag.name == "td":
                attrs = {}
                for attr_name in ("rowspan", "colspan"):
                    attr_value = tag.get(attr_name)
                    if attr_value:
                        attrs[attr_name] = attr_value
                tag.attrs = attrs
            elif tag.name == "th":
                attrs = {}
                for attr_name in ("rowspan", "colspan", "scope"):
                    attr_value = tag.get(attr_name)
                    if attr_value:
                        attrs[attr_name] = attr_value
                tag.attrs = attrs
            else:
                tag.attrs = {}

        IntermediateParser._wrap_loose_text(document.body)
        IntermediateParser._split_invalid_paragraphs(document)
        IntermediateParser._normalize_whitespace_nodes(document)
        IntermediateParser._remove_empty_tags(document)

    @staticmethod
    def _split_invalid_paragraphs(document: BeautifulSoup) -> None:
        inline_tags = {"a", "br"}
        paragraph_blockers = IntermediateParser.BLOCK_TAGS

        for paragraph in list(document.find_all("p")):
            if not any(
                isinstance(child, Tag) and child.name in paragraph_blockers
                for child in paragraph.children
            ):
                continue

            parent = paragraph.parent
            if not parent:
                continue

            insert_before = paragraph
            inline_buffer: list[Tag | NavigableString] = []

            def flush_inline_buffer() -> None:
                nonlocal insert_before
                if not inline_buffer:
                    return

                new_paragraph = document.new_tag("p")
                for node in inline_buffer:
                    new_paragraph.append(node.extract())
                insert_before.insert_before(new_paragraph)
                inline_buffer.clear()

            for child in list(paragraph.contents):
                if isinstance(child, NavigableString):
                    if IntermediateParser._clean_text(str(child)):
                        inline_buffer.append(child)
                    else:
                        child.extract()
                    continue

                if child.name in inline_tags:
                    inline_buffer.append(child)
                    continue

                flush_inline_buffer()
                insert_before.insert_before(child.extract())

            flush_inline_buffer()
            paragraph.decompose()

    @staticmethod
    def _normalize_whitespace_nodes(fragment: BeautifulSoup | Tag) -> None:
        for child in list(fragment.children):
            if isinstance(child, NavigableString):
                text = str(child)
                if not text.strip():
                    child.extract()
                    continue

                normalized = IntermediateParser._clean_text(text)
                if normalized != text:
                    child.replace_with(normalized)
                continue

            IntermediateParser._normalize_whitespace_nodes(child)

    @staticmethod
    def _wrap_loose_text(body: Tag) -> None:
        for child in list(body.children):
            if not isinstance(child, NavigableString):
                continue

            text = IntermediateParser._clean_text(str(child))
            if not text:
                child.extract()
                continue

            child.replace_with(IntermediateParser._new_paragraph(text))

    @staticmethod
    def _remove_empty_tags(document: BeautifulSoup) -> None:
        for tag in reversed(document.find_all(True)):
            if tag.name in {"br", "html", "body"}:
                continue

            text = IntermediateParser._clean_text(tag.get_text(" ", strip=True))
            if text:
                continue

            if tag.find(True):
                continue

            tag.decompose()

    @staticmethod
    def _remove_comments(fragment: BeautifulSoup) -> None:
        for comment in fragment.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

    @staticmethod
    def _remove_noise(fragment: BeautifulSoup) -> None:
        for tag in fragment.find_all(["img", "script", "style"]):
            tag.decompose()

    @staticmethod
    def _unwrap_tag_name(fragment: BeautifulSoup, tag_name: str) -> None:
        for tag in fragment.find_all(tag_name):
            tag.unwrap()

    @staticmethod
    def _strings_from_selector(source: BeautifulSoup, selector: str) -> list[str]:
        items = []
        for tag in source.select(selector):
            items.extend(IntermediateParser._strings_from_tag(tag))
        return items

    @staticmethod
    def _strings_from_tag(tag: Tag | None) -> list[str]:
        if not tag:
            return []
        return [
            IntermediateParser._clean_text(text)
            for text in tag.stripped_strings
            if IntermediateParser._clean_text(text)
        ]

    @staticmethod
    def _clean_text(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _new_paragraph(text: str) -> Tag:
        soup = BeautifulSoup("", "html.parser")
        paragraph = soup.new_tag("p")
        paragraph.string = text
        return paragraph

    @staticmethod
    def _preserve_italic_semantics(fragment: BeautifulSoup) -> None:
        for tag in fragment.find_all(True):
            classes = set(tag.get("class", []))
            if "italic" not in classes:
                continue

            has_em_child = any(
                isinstance(child, Tag) and child.name == "em"
                for child in tag.contents
            )
            if has_em_child:
                continue

            text = IntermediateParser._clean_text(tag.get_text(" ", strip=True))
            if not text:
                continue

            tag.clear()
            emphasis = fragment.new_tag("em")
            emphasis.string = text
            tag.append(emphasis)

    @staticmethod
    def _normalize_anslag_summary_tables(document: BeautifulSoup) -> None:
        body = document.body
        if not body:
            return

        children = list(body.find_all(recursive=False))
        i = 0

        while i < len(children):
            tag = children[i]
            if not IntermediateParser._is_tilldelade_anslag_heading(tag):
                i += 1
                continue

            j = i + 1
            while j < len(children) and not IntermediateParser._is_heading(children[j]):
                j += 1

            region = children[i + 1 : j]
            IntermediateParser._normalize_anslag_region(document, region)
            children = list(body.find_all(recursive=False))
            i = j

    @staticmethod
    def _normalize_anslag_region(document: BeautifulSoup, region: list[Tag]) -> None:
        i = 0
        while i < len(region):
            tag = region[i]
            if IntermediateParser._is_anslag_title_paragraph(tag):
                normalized_table, consumed = IntermediateParser._build_anslag_table_from_sequence(
                    document,
                    tag,
                    region,
                    i,
                )
                if normalized_table:
                    tag.replace_with(normalized_table)
                    for sibling in region[i + 1 : i + consumed]:
                        sibling.decompose()
                    i += consumed
                    continue

            if IntermediateParser._is_anslag_title_table(tag):
                normalized_table, consumed = IntermediateParser._build_anslag_table_from_sequence(
                    document,
                    tag,
                    region,
                    i,
                )
                if normalized_table:
                    tag.replace_with(normalized_table)
                    for sibling in region[i + 1 : i + consumed]:
                        sibling.decompose()
                    i += consumed
                    continue

            if IntermediateParser._is_combined_anslag_table(tag):
                normalized_table = IntermediateParser._build_anslag_table_from_combined_table(
                    document,
                    tag,
                )
                if normalized_table:
                    tag.replace_with(normalized_table)

            i += 1

    @staticmethod
    def _build_anslag_table_from_sequence(
        document: BeautifulSoup,
        title_tag: Tag,
        region: list[Tag],
        start_index: int,
    ) -> tuple[Tag | None, int]:
        anslag_code, anslag_name = IntermediateParser._parse_anslag_title(title_tag)
        if not anslag_code or not anslag_name:
            return None, 0

        rows = []
        consumed = 1
        current_disposition = ""
        current_disposition_amount = ""

        for sibling in region[start_index + 1 :]:
            if IntermediateParser._is_anslag_disposition_table(sibling):
                disposition = IntermediateParser._parse_disposition_row(sibling)
                if not disposition:
                    break
                current_disposition, current_disposition_amount = disposition
                consumed += 1
                continue

            if IntermediateParser._is_anslag_ap_table(sibling):
                ap_rows = IntermediateParser._parse_ap_rows(sibling)
                if not ap_rows:
                    break
                for post_code, post_name, post_amount in ap_rows:
                    rows.append(
                        [
                            anslag_code,
                            anslag_name,
                            current_disposition,
                            current_disposition_amount,
                            post_code,
                            post_name,
                            post_amount,
                        ]
                    )
                consumed += 1
                continue

            break

        if not rows:
            return None, 0

        return IntermediateParser._build_semantic_anslag_table(document, rows), consumed

    @staticmethod
    def _build_anslag_table_from_combined_table(
        document: BeautifulSoup, table: Tag
    ) -> Tag | None:
        rows = []
        anslag_code = ""
        anslag_name = ""
        current_disposition = ""
        current_disposition_amount = ""

        for row in table.find_all("tr", recursive=False):
            cells = [
                IntermediateParser._clean_text(cell.get_text(" ", strip=True))
                for cell in row.find_all(["td", "th"], recursive=False)
            ]
            cells = [cell for cell in cells if cell]
            if not cells:
                continue

            if len(cells) >= 2 and re.fullmatch(r"\d+:\d+", cells[0]):
                anslag_code = cells[0]
                anslag_name = cells[1]
                continue

            if cells[0].startswith("Disponeras av"):
                current_disposition = cells[0]
                current_disposition_amount = cells[-1] if len(cells) > 1 else ""
                continue

            if re.fullmatch(r"(?:\d+:\d+\s+)?ap\.\d+(?:\.\d+)?", cells[0]):
                post_code = cells[0]
                post_name = cells[1] if len(cells) > 1 else ""
                post_amount = cells[-1] if len(cells) > 2 else ""
                rows.append(
                    [
                        anslag_code,
                        anslag_name,
                        current_disposition,
                        current_disposition_amount,
                        post_code,
                        post_name,
                        post_amount,
                    ]
                )

        if not rows:
            return None

        return IntermediateParser._build_semantic_anslag_table(document, rows)

    @staticmethod
    def _build_semantic_anslag_table(document: BeautifulSoup, rows: list[list[str]]) -> Tag:
        table = document.new_tag("table")
        thead = document.new_tag("thead")
        tbody = document.new_tag("tbody")
        table.append(thead)
        table.append(tbody)

        header_row = document.new_tag("tr")
        for label in [
            "Anslag",
            "Benamning",
            "Disponeras av",
            "Dispositionsbelopp",
            "Anslagspost",
            "Postbenamning",
            "Postbelopp",
        ]:
            th = document.new_tag("th")
            th.string = label
            header_row.append(th)
        thead.append(header_row)

        for row_data in rows:
            tr = document.new_tag("tr")
            for value in row_data:
                td = document.new_tag("td")
                td.string = value
                tr.append(td)
            tbody.append(tr)

        return table

    @staticmethod
    def _is_tilldelade_anslag_heading(tag: Tag) -> bool:
        return IntermediateParser._is_heading(tag) and "tilldelade anslag" in (
            IntermediateParser._clean_text(tag.get_text(" ", strip=True)).lower()
        )

    @staticmethod
    def _is_heading(tag: Tag) -> bool:
        return tag.name in {"h1", "h2", "h3", "h4", "h5", "h6"}

    @staticmethod
    def _is_anslag_title_paragraph(tag: Tag) -> bool:
        if tag.name != "p":
            return False
        strong = tag.find("strong", recursive=False)
        if not strong:
            return False
        text = IntermediateParser._clean_text(strong.get_text(" ", strip=True))
        return bool(re.match(r"^\d+:\d+\s", text))

    @staticmethod
    def _is_anslag_title_table(tag: Tag) -> bool:
        if tag.name != "table":
            return False
        rows = tag.find_all("tr", recursive=False)
        if len(rows) != 1:
            return False
        cells = rows[0].find_all(["td", "th"], recursive=False)
        if len(cells) != 2:
            return False
        first = IntermediateParser._clean_text(cells[0].get_text(" ", strip=True))
        second = IntermediateParser._clean_text(cells[1].get_text(" ", strip=True))
        return bool(re.fullmatch(r"\d+:\d+", first) and second and not second.startswith("Disponeras av"))

    @staticmethod
    def _is_combined_anslag_table(tag: Tag) -> bool:
        if tag.name != "table":
            return False
        text = IntermediateParser._clean_text(tag.get_text(" ", strip=True))
        return "Disponeras av" in text and bool(re.search(r"\bap\.\d+", text))

    @staticmethod
    def _is_anslag_disposition_table(tag: Tag) -> bool:
        if tag.name != "table":
            return False
        first_row = tag.find("tr", recursive=False)
        if not first_row:
            return False
        first_cell = first_row.find(["td", "th"], recursive=False)
        if not first_cell:
            return False
        text = IntermediateParser._clean_text(first_cell.get_text(" ", strip=True))
        return text.startswith("Disponeras av")

    @staticmethod
    def _is_anslag_ap_table(tag: Tag) -> bool:
        if tag.name != "table":
            return False
        first_row = tag.find("tr", recursive=False)
        if not first_row:
            return False
        first_cell = first_row.find(["td", "th"], recursive=False)
        if not first_cell:
            return False
        text = IntermediateParser._clean_text(first_cell.get_text(" ", strip=True))
        return bool(re.fullmatch(r"(?:\d+:\d+\s+)?ap\.\d+(?:\.\d+)?", text))

    @staticmethod
    def _parse_anslag_title(tag: Tag) -> tuple[str, str]:
        if tag.name == "p":
            text = IntermediateParser._clean_text(tag.get_text(" ", strip=True))
            match = re.match(r"^(\d+:\d+)\s+(.+)$", text)
            if match:
                return match.group(1), match.group(2)
            return "", ""

        row = tag.find("tr", recursive=False)
        if not row:
            return "", ""
        cells = row.find_all(["td", "th"], recursive=False)
        if len(cells) != 2:
            return "", ""
        return (
            IntermediateParser._clean_text(cells[0].get_text(" ", strip=True)),
            IntermediateParser._clean_text(cells[1].get_text(" ", strip=True)),
        )

    @staticmethod
    def _parse_disposition_row(tag: Tag) -> tuple[str, str] | None:
        row = tag.find("tr", recursive=False)
        if not row:
            return None
        cells = [
            IntermediateParser._clean_text(cell.get_text(" ", strip=True))
            for cell in row.find_all(["td", "th"], recursive=False)
        ]
        cells = [cell for cell in cells if cell]
        if not cells or not cells[0].startswith("Disponeras av"):
            return None
        return cells[0], cells[-1] if len(cells) > 1 else ""

    @staticmethod
    def _parse_ap_rows(tag: Tag) -> list[tuple[str, str, str]]:
        rows = []
        for row in tag.find_all("tr", recursive=False):
            cells = [
                IntermediateParser._clean_text(cell.get_text(" ", strip=True))
                for cell in row.find_all(["td", "th"], recursive=False)
            ]
            cells = [cell for cell in cells if cell]
            if not cells:
                continue
            if not re.fullmatch(r"(?:\d+:\d+\s+)?ap\.\d+(?:\.\d+)?", cells[0]):
                continue
            rows.append(
                (
                    cells[0],
                    cells[1] if len(cells) > 1 else "",
                    cells[-1] if len(cells) > 2 else "",
                )
            )
        return rows
