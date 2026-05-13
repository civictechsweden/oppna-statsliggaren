import re
from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from services.template_classifier import TemplateVariant, classify_letter_template
from services.xhtml_extractor import XHTMLExtractor
from services.xhtml_outline import XHTMLOutlineNormalizer
from services.xhtml_serializer import XHTMLSerializer


class IntermediateParser(object):
    SEMANTIC_CLASSES = {
        "document-title",
        "letterhead",
        "letterhead-department",
        "letterhead-decision",
        "letterhead-decision-number",
        "letterhead-date",
        "letterhead-diary",
        "letterhead-recipient",
    }

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
        "sup",
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
        IntermediateParser._normalize_policy_outline_blocks(document)
        XHTMLOutlineNormalizer.normalize(document, IntermediateParser._clean_text)
        IntermediateParser._normalize_label_paragraphs(document)
        IntermediateParser._normalize_footer_signature_tables(document)
        IntermediateParser._normalize_anslag_summary_tables(document)
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
        IntermediateParser._promote_footnotes(fragment)
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

            if not texts:
                continue

            if len(texts) == 1:
                if not heading_levels:
                    continue
                level = min(heading_levels)
                heading = fragment.new_tag(f"h{level}")
                heading.string = texts[0]
                table.replace_with(heading)
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
        IntermediateParser._unwrap_layout_tables(document)

        for tag in list(document.find_all(True)):
            if tag.name not in IntermediateParser.ALLOWED_TAGS:
                tag.unwrap()
                continue

            if tag.name == "a":
                href = tag.get("href")
                tag.attrs = {"href": href} if href else {}
            elif tag.name == "table":
                attrs = {}
                tag_class = tag.get("class")
                normalized_class = IntermediateParser._semantic_class_value(tag_class)
                if normalized_class:
                    attrs["class"] = normalized_class
                tag.attrs = attrs
            elif tag.name == "td":
                attrs = {}
                tag_class = tag.get("class")
                normalized_class = IntermediateParser._semantic_class_value(tag_class)
                if normalized_class:
                    attrs["class"] = normalized_class
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
            elif tag.name in {"h1", "p"}:
                attrs = {}
                tag_class = tag.get("class")
                normalized_class = IntermediateParser._semantic_class_value(tag_class)
                if normalized_class:
                    attrs["class"] = normalized_class
                tag.attrs = attrs
            else:
                tag.attrs = {}

        IntermediateParser._wrap_loose_text(document.body)
        IntermediateParser._wrap_orphan_inline_body_nodes(document)
        IntermediateParser._normalize_heading_contents(document)
        IntermediateParser._split_invalid_paragraphs(document)
        IntermediateParser._remove_body_level_breaks(document)
        IntermediateParser._collapse_redundant_breaks(document)
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
    def _unwrap_layout_tables(fragment: BeautifulSoup | Tag) -> None:
        changed = True
        while changed:
            changed = False
            for table in list(fragment.find_all("table")):
                rows = IntermediateParser._table_rows(table)
                if len(rows) != 1:
                    continue

                cells = rows[0].find_all(["td", "th"], recursive=False)
                if len(cells) != 1:
                    continue

                cell = cells[0]
                if cell.get("rowspan") or cell.get("colspan"):
                    continue

                if not any(isinstance(child, Tag) for child in cell.contents):
                    continue

                for child in list(cell.contents):
                    table.insert_before(child.extract())
                table.decompose()
                changed = True
                break

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
    def _semantic_class_value(tag_class) -> str | None:
        class_names = tag_class if isinstance(tag_class, list) else [tag_class] if tag_class else []
        semantic = [class_name for class_name in class_names if class_name in IntermediateParser.SEMANTIC_CLASSES]
        if not semantic:
            return None
        return " ".join(semantic)

    @staticmethod
    def _normalize_heading_contents(document: BeautifulSoup) -> None:
        for heading in document.find_all(re.compile(r"^h[1-6]$")):
            text = IntermediateParser._clean_text(heading.get_text(" ", strip=True))
            if not text:
                continue

            if any(
                isinstance(child, Tag) and child.name in IntermediateParser.BLOCK_TAGS
                for child in heading.contents
            ):
                heading.clear()
                heading.string = text

    @staticmethod
    def _wrap_orphan_inline_body_nodes(document: BeautifulSoup) -> None:
        body = document.body
        if not body:
            return

        inline_tags = {"a", "em", "strong", "sup"}
        for child in list(body.children):
            if not isinstance(child, Tag) or child.name not in inline_tags:
                continue

            paragraph = document.new_tag("p")
            child.replace_with(paragraph)
            paragraph.append(child)

    @staticmethod
    def _remove_body_level_breaks(document: BeautifulSoup) -> None:
        body = document.body
        if not body:
            return

        for child in list(body.children):
            if isinstance(child, Tag) and child.name == "br":
                child.decompose()

    @staticmethod
    def _collapse_redundant_breaks(fragment: BeautifulSoup | Tag) -> None:
        for parent in fragment.find_all(True):
            previous_was_br = False
            for child in list(parent.contents):
                if isinstance(child, Tag) and child.name == "br":
                    if previous_was_br:
                        child.decompose()
                        continue
                    previous_was_br = True
                    continue

                if isinstance(child, NavigableString) and not IntermediateParser._clean_text(str(child)):
                    child.extract()
                    continue

                previous_was_br = False

    @staticmethod
    def _normalize_label_paragraphs(document: BeautifulSoup) -> None:
        body = document.body
        if not body:
            return

        for paragraph in body.find_all("p", recursive=False):
            if paragraph.find("strong", recursive=False):
                continue

            if any(isinstance(child, Tag) and child.name != "br" for child in paragraph.contents):
                continue

            text = IntermediateParser._clean_text(paragraph.get_text(" ", strip=True))
            if not text:
                continue

            if not (
                XHTMLOutlineNormalizer._is_label_heading(text)
                or XHTMLOutlineNormalizer._is_local_numbered_label(text)
            ):
                continue

            strong = document.new_tag("strong")
            strong.string = text
            paragraph.clear()
            paragraph.append(strong)

    @staticmethod
    def _normalize_policy_outline_blocks(document: BeautifulSoup) -> None:
        body = document.body
        if not body:
            return

        children = list(body.find_all(recursive=False))
        index = 0
        while index < len(children):
            child = children[index]
            if child.name != "p":
                index += 1
                continue

            fragments = IntermediateParser._policy_outline_fragments_from_tag(child)
            if not fragments or not any(
                fragment.startswith("PO ")
                or fragment.startswith("VO ")
                or fragment.startswith("VG ")
                or fragment.startswith("- VO ")
                or fragment.startswith("- VG ")
                for fragment in fragments
            ):
                index += 1
                continue

            single_lines = IntermediateParser._parse_policy_outline_lines([child])
            if len(single_lines) >= 2:
                new_nodes = [
                    IntermediateParser._new_policy_outline_paragraph(document, line)
                    for line in single_lines
                ]
                for new_node in new_nodes:
                    child.insert_before(new_node)
                child.decompose()
                children = list(body.find_all(recursive=False))
                index += len(new_nodes)
                continue

            sequence = [child]
            next_index = index + 1
            while next_index < len(children):
                sibling = children[next_index]
                if sibling.name == "br":
                    sequence.append(sibling)
                    next_index += 1
                    continue
                if sibling.name == "p":
                    sibling_fragments = IntermediateParser._policy_outline_fragments_from_tag(sibling)
                    pending_role = IntermediateParser._policy_outline_pending_role(sequence)
                    if sibling_fragments and (
                        IntermediateParser._looks_like_policy_outline_fragment_block(
                            sibling_fragments
                        )
                        or (
                            pending_role
                            and not any(
                                re.match(r"^\-?\s*(PO|VO|VG)\b", fragment)
                                for fragment in sibling_fragments
                            )
                        )
                    ):
                        sequence.append(sibling)
                        next_index += 1
                        continue
                    if not sibling_fragments and (
                        pending_role
                        or IntermediateParser._policy_outline_has_any_role(sequence)
                    ):
                        sequence.append(sibling)
                        next_index += 1
                        continue
                break

            normalized_lines = IntermediateParser._parse_policy_outline_lines(sequence)
            if len(normalized_lines) >= 2:
                new_nodes = [
                    IntermediateParser._new_policy_outline_paragraph(document, line)
                    for line in normalized_lines
                ]
                first = sequence[0]
                for new_node in new_nodes:
                    first.insert_before(new_node)
                for node in sequence:
                    node.decompose()
                children = list(body.find_all(recursive=False))
                index += len(new_nodes)
                continue

            index = next_index

    @staticmethod
    def _policy_outline_fragments_from_tag(tag: Tag) -> list[str]:
        if tag.name != "p":
            return []

        text = tag.get_text("\n", strip=True)
        return [
            IntermediateParser._clean_text(fragment)
            for fragment in text.split("\n")
            if IntermediateParser._clean_text(fragment)
        ]

    @staticmethod
    def _looks_like_policy_outline_fragment_block(fragments: list[str]) -> bool:
        allowed_prefixes = (
            "PO ",
            "VO ",
            "VG ",
            "-",
        )
        return all(
            fragment.startswith(allowed_prefixes) or fragment in {"VO", "VG"}
            for fragment in fragments
        )

    @staticmethod
    def _parse_policy_outline_lines(sequence: list[Tag]) -> list[tuple[str, str]]:
        fragments = []
        for node in sequence:
            if node.name != "p":
                continue
            fragments.extend(IntermediateParser._policy_outline_fragments_from_tag(node))

        values, _ = IntermediateParser._policy_outline_state_from_fragments(fragments)
        lines = []
        for role in ["PO", "VO", "VG"]:
            value = values.get(role, "").strip()
            if value:
                lines.append((role, value))
        return lines

    @staticmethod
    def _policy_outline_pending_role(sequence: list[Tag]) -> str | None:
        fragments = []
        for node in sequence:
            if node.name != "p":
                continue
            fragments.extend(IntermediateParser._policy_outline_fragments_from_tag(node))

        _, pending_role = IntermediateParser._policy_outline_state_from_fragments(fragments)
        return pending_role

    @staticmethod
    def _policy_outline_has_any_role(sequence: list[Tag]) -> bool:
        return bool(IntermediateParser._parse_policy_outline_lines(sequence))

    @staticmethod
    def _policy_outline_state_from_fragments(
        fragments: list[str],
    ) -> tuple[dict[str, str], str | None]:
        values = {}
        current_role = None
        for fragment in fragments:
            normalized = re.sub(r"^\-\s*", "", fragment).strip()
            if normalized in {"VO", "VG"}:
                current_role = normalized
                values.setdefault(current_role, "")
                continue

            role_match = re.match(r"^(PO|VO|VG)\s+(.*)$", normalized)
            if role_match:
                current_role = role_match.group(1)
                values[current_role] = role_match.group(2).strip()
                continue

            if current_role:
                existing = values.get(current_role, "")
                values[current_role] = f"{existing} {normalized}".strip() if existing else normalized

        pending_role = (
            current_role
            if current_role in {"VO", "VG"} and not values.get(current_role, "").strip()
            else None
        )
        return values, pending_role

    @staticmethod
    def _new_policy_outline_paragraph(document: BeautifulSoup, line: tuple[str, str]) -> Tag:
        role, value = line
        paragraph = document.new_tag("p")

        if role == "PO":
            strong = document.new_tag("strong")
            strong.string = f"{role} {value}"
            paragraph.append(strong)
            return paragraph

        if role == "VO":
            strong = document.new_tag("strong")
            emphasis = document.new_tag("em")
            emphasis.string = f"{role} {value}"
            strong.append(emphasis)
            paragraph.append(strong)
            return paragraph

        emphasis = document.new_tag("em")
        emphasis.string = f"{role} {value}"
        paragraph.append(emphasis)
        return paragraph

    @staticmethod
    def _normalize_footer_signature_tables(document: BeautifulSoup) -> None:
        body = document.body
        if not body:
            return

        children = list(body.find_all(recursive=False))
        for index, child in enumerate(children[:-1]):
            if child.name != "p":
                continue

            text = IntermediateParser._clean_text(child.get_text(" ", strip=True))
            if text != "På regeringens vägnar":
                continue

            table = children[index + 1]
            if not IntermediateParser._is_simple_signature_table(table):
                continue

            paragraphs = []
            for row in IntermediateParser._table_rows(table):
                cell = row.find(["td", "th"], recursive=False)
                if not cell:
                    continue
                cell_text = IntermediateParser._clean_text(cell.get_text(" ", strip=True))
                if not cell_text:
                    continue
                paragraphs.append(IntermediateParser._new_paragraph(cell_text))

            if not paragraphs:
                table.decompose()
                continue

            current = table
            for paragraph in paragraphs:
                current.insert_before(paragraph)
            table.decompose()

    @staticmethod
    def _is_simple_signature_table(tag: Tag) -> bool:
        if tag.name != "table":
            return False

        rows = IntermediateParser._table_rows(tag)
        if not rows:
            return False

        for row in rows:
            cells = row.find_all(["td", "th"], recursive=False)
            if len(cells) != 1:
                return False

            cell = cells[0]
            if cell.get("rowspan") or cell.get("colspan"):
                return False

            if any(isinstance(desc, Tag) and desc.name not in {"br"} for desc in cell.find_all(True)):
                return False

        return True

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
    def _promote_footnotes(fragment: BeautifulSoup) -> None:
        for tag in list(fragment.find_all(True)):
            classes = set(tag.get("class", []))
            if "fotnot" not in classes:
                continue

            lines = IntermediateParser._extract_footnote_lines(tag)
            if not lines:
                tag.decompose()
                continue

            paragraphs = []
            for line in lines:
                paragraph = fragment.new_tag("p")
                emphasis = fragment.new_tag("em")
                for node in line:
                    emphasis.append(node)
                paragraph.append(emphasis)
                paragraphs.append(paragraph)

            replacement = paragraphs[0]
            tag.replace_with(replacement)
            current = replacement
            for paragraph in paragraphs[1:]:
                current.insert_after(paragraph)
                current = paragraph

    @staticmethod
    def _extract_footnote_lines(tag: Tag) -> list[list[Tag | NavigableString]]:
        lines: list[list[Tag | NavigableString]] = [[]]

        for child in list(tag.contents):
            if isinstance(child, Tag) and child.name == "br":
                if lines[-1]:
                    lines.append([])
                child.extract()
                continue

            if isinstance(child, NavigableString):
                text = IntermediateParser._clean_text(str(child))
                child.extract()
                if not text:
                    continue
                node = NavigableString(text)
                if (
                    lines[-1]
                    and isinstance(lines[-1][-1], Tag)
                    and lines[-1][-1].name == "sup"
                ):
                    lines[-1].append(NavigableString(f" {text}"))
                else:
                    lines[-1].append(node)
                continue

            child.extract()
            child.attrs = {}
            lines[-1].append(child)

        return [line for line in lines if any(IntermediateParser._clean_text(str(node)) for node in line)]

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

            current_level = int(tag.name[1])
            j = i + 1
            while j < len(children):
                next_tag = children[j]
                if IntermediateParser._is_heading(next_tag):
                    next_level = int(next_tag.name[1])
                    if next_level <= current_level:
                        break
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
                title_paragraph, normalized_table, consumed = IntermediateParser._build_anslag_table_from_sequence(
                    document,
                    tag,
                    region,
                    i,
                )
                if normalized_table:
                    tag.replace_with(title_paragraph)
                    title_paragraph.insert_after(normalized_table)
                    for sibling in region[i + 1 : i + consumed]:
                        sibling.decompose()
                    i += consumed
                    continue

            if IntermediateParser._is_anslag_title_table(tag):
                title_paragraph, normalized_table, consumed = IntermediateParser._build_anslag_table_from_sequence(
                    document,
                    tag,
                    region,
                    i,
                )
                if normalized_table:
                    tag.replace_with(title_paragraph)
                    title_paragraph.insert_after(normalized_table)
                    for sibling in region[i + 1 : i + consumed]:
                        sibling.decompose()
                    i += consumed
                    continue

            if IntermediateParser._is_combined_anslag_table(tag):
                title_paragraph, normalized_table = IntermediateParser._build_anslag_table_from_combined_table(
                    document,
                    tag,
                )
                if normalized_table and title_paragraph:
                    tag.replace_with(title_paragraph)
                    title_paragraph.insert_after(normalized_table)

            i += 1

    @staticmethod
    def _build_anslag_table_from_sequence(
        document: BeautifulSoup,
        title_tag: Tag,
        region: list[Tag],
        start_index: int,
    ) -> tuple[Tag | None, Tag | None, int]:
        anslag_code, anslag_name = IntermediateParser._parse_anslag_title(title_tag)
        if not anslag_code or not anslag_name:
            return None, None, 0

        table_rows = []
        consumed = 1
        current_disposition = ""
        current_disposition_amount = ""
        ap_header = None

        for sibling in region[start_index + 1 :]:
            if IntermediateParser._is_combined_anslag_table(sibling):
                ap_header, combined_rows = IntermediateParser._parse_combined_ap_rows(
                    sibling,
                    current_disposition,
                    current_disposition_amount,
                )
                if not combined_rows:
                    break
                table_rows.extend(combined_rows)
                consumed += 1
                continue

            if IntermediateParser._is_anslag_disposition_table(sibling):
                disposition = IntermediateParser._parse_disposition_row(sibling)
                if not disposition:
                    break
                current_disposition, current_disposition_amount = disposition
                table_rows.append(
                    IntermediateParser._build_disposition_table_row(
                        current_disposition,
                        current_disposition_amount,
                    )
                )
                consumed += 1
                continue

            if IntermediateParser._is_anslag_ap_table(sibling):
                ap_header, ap_rows = IntermediateParser._parse_ap_rows(sibling)
                if not ap_rows:
                    break
                table_rows.extend(ap_rows)
                consumed += 1
                continue

            break

        if not table_rows:
            return None, None, 0

        return (
            IntermediateParser._build_anslag_title_paragraph(
                document, f"{anslag_code} {anslag_name}"
            ),
            IntermediateParser._build_merged_anslag_table(document, ap_header, table_rows),
            consumed,
        )

    @staticmethod
    def _build_anslag_table_from_combined_table(
        document: BeautifulSoup, table: Tag
    ) -> tuple[Tag | None, Tag | None]:
        anslag_code = ""
        anslag_name = ""
        first_title = IntermediateParser._parse_anslag_title(table)
        if first_title != ("", ""):
            anslag_code, anslag_name = first_title

        ap_header, rows = IntermediateParser._parse_combined_ap_rows(
            table,
            "",
            "",
        )
        if not rows:
            return None, None

        title_paragraph = None
        if anslag_code and anslag_name:
            title_paragraph = IntermediateParser._build_anslag_title_paragraph(
                document, f"{anslag_code} {anslag_name}"
            )
        return title_paragraph, IntermediateParser._build_merged_anslag_table(
            document, ap_header, rows
        )

    @staticmethod
    def _build_merged_anslag_table(
        document: BeautifulSoup, ap_header: list[str] | None, rows: list[tuple]
    ) -> Tag:
        table = document.new_tag("table")
        tbody = document.new_tag("tbody")
        table.append(tbody)

        if ap_header:
            header_row = document.new_tag("tr")
            for label in ap_header:
                th = document.new_tag("th")
                th.string = label
                header_row.append(th)
            tbody.append(header_row)

        for row_data in rows:
            kind = row_data[0]
            tr = document.new_tag("tr")
            if kind == "disposition":
                left = document.new_tag("td")
                left["colspan"] = "2"
                left.string = row_data[1]
                amount = document.new_tag("td")
                amount.string = row_data[2]
                tr.append(left)
                tr.append(amount)
            elif kind == "ap":
                for value in row_data[1:]:
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
        rows = IntermediateParser._table_rows(tag)
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
        rows = IntermediateParser._table_rows(tag)
        if not rows:
            return False
        first_row = rows[0]
        first_cell = first_row.find(["td", "th"], recursive=False)
        if not first_cell:
            return False
        text = IntermediateParser._clean_text(first_cell.get_text(" ", strip=True))
        return text.startswith("Disponeras av")

    @staticmethod
    def _is_anslag_ap_table(tag: Tag) -> bool:
        if tag.name != "table":
            return False
        return bool(IntermediateParser._parse_ap_rows(tag))

    @staticmethod
    def _parse_anslag_title(tag: Tag) -> tuple[str, str]:
        if tag.name == "p":
            text = IntermediateParser._clean_text(tag.get_text(" ", strip=True))
            match = re.match(r"^(\d+:\d+)\s+(.+)$", text)
            if match:
                return match.group(1), match.group(2)
            return "", ""

        rows = IntermediateParser._table_rows(tag)
        if not rows:
            return "", ""
        row = rows[0]
        cells = row.find_all(["td", "th"], recursive=False)
        if len(cells) != 2:
            return "", ""
        return (
            IntermediateParser._clean_text(cells[0].get_text(" ", strip=True)),
            IntermediateParser._clean_text(cells[1].get_text(" ", strip=True)),
        )

    @staticmethod
    def _parse_disposition_row(tag: Tag) -> tuple[str, str] | None:
        rows = IntermediateParser._table_rows(tag)
        if not rows:
            return None
        row = rows[0]
        cells = [
            IntermediateParser._clean_text(cell.get_text(" ", strip=True))
            for cell in row.find_all(["td", "th"], recursive=False)
        ]
        cells = [cell for cell in cells if cell]
        if not cells or not cells[0].startswith("Disponeras av"):
            return None
        return cells[0], cells[-1] if len(cells) > 1 else ""

    @staticmethod
    def _parse_ap_rows(tag: Tag) -> tuple[list[str] | None, list[tuple[str, str, str, str]]]:
        header = None
        rows = []
        for index, row in enumerate(IntermediateParser._table_rows(tag)):
            cells = [
                IntermediateParser._clean_text(cell.get_text(" ", strip=True))
                for cell in row.find_all(["td", "th"], recursive=False)
            ]
            cells = [cell for cell in cells if cell]
            if not cells:
                continue
            if index == 0 and not re.fullmatch(r"(?:\d+:\d+\s+)?ap\.\d+(?:\.\d+)?", cells[0]):
                if len(cells) >= 3:
                    header = cells[:3]
                continue
            if not re.fullmatch(r"(?:\d+:\d+\s+)?ap\.\d+(?:\.\d+)?", cells[0]):
                continue
            rows.append(
                (
                    "ap",
                    cells[0],
                    cells[1] if len(cells) > 1 else "",
                    cells[-1] if len(cells) > 2 else "",
                )
            )
        return header, rows

    @staticmethod
    def _parse_combined_ap_rows(
        tag: Tag,
        initial_disposition: str,
        initial_disposition_amount: str,
    ) -> tuple[list[str] | None, list[tuple]]:
        rows = []
        current_disposition = initial_disposition
        current_disposition_amount = initial_disposition_amount
        header = None

        for index, row in enumerate(IntermediateParser._table_rows(tag)):
            cells = [
                IntermediateParser._clean_text(cell.get_text(" ", strip=True))
                for cell in row.find_all(["td", "th"], recursive=False)
            ]
            cells = [cell for cell in cells if cell]
            if not cells:
                continue

            if index == 0 and len(cells) >= 3 and cells[0].lower() in {"nomenklatur", "anslag/ap", "anslag/ap/dp"}:
                header = cells[:3]
                continue

            if cells[0].startswith("Disponeras av"):
                current_disposition = cells[0]
                current_disposition_amount = cells[-1] if len(cells) > 1 else ""
                rows.append(
                    IntermediateParser._build_disposition_table_row(
                        current_disposition,
                        current_disposition_amount,
                    )
                )
                continue

            if re.fullmatch(r"(?:\d+:\d+\s+)?ap\.\d+(?:\.\d+)?", cells[0]):
                rows.append(
                    (
                        "ap",
                        cells[0],
                        cells[1] if len(cells) > 1 else "",
                        cells[-1] if len(cells) > 2 else "",
                    )
                )

        return header, rows

    @staticmethod
    def _build_disposition_table_row(disposition: str, amount: str) -> tuple[str, str, str]:
        return ("disposition", disposition, amount)

    @staticmethod
    def _build_anslag_title_paragraph(document: BeautifulSoup, text: str) -> Tag:
        paragraph = document.new_tag("p")
        strong = document.new_tag("strong")
        strong.string = text
        paragraph.append(strong)
        return paragraph

    @staticmethod
    def _table_rows(table: Tag) -> list[Tag]:
        rows = table.find_all("tr", recursive=False)
        if rows:
            return rows

        for section_name in ("thead", "tbody"):
            section = table.find(section_name, recursive=False)
            if section:
                rows.extend(section.find_all("tr", recursive=False))

        return rows
