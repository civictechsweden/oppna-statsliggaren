import re

from selectolax.lexbor import LexborNode

from services import html_dom as dom
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
        source = dom.parse_html(html)
        document = dom.parse_html("<html><body></body></html>")
        body = dom.find(document, "body")

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
        return XHTMLSerializer.serialize_document(
            document, IntermediateParser._clean_text
        )

    @staticmethod
    def _append_extracted_content(
        body: LexborNode, extracted, variant: TemplateVariant
    ) -> None:
        if extracted.header_lines:
            IntermediateParser._append_text_lines(body, extracted.header_lines)
        if extracted.header_fragment:
            IntermediateParser._append_fragment(
                body, extracted.header_fragment, variant
            )
        if extracted.body_fragment:
            IntermediateParser._append_fragment(body, extracted.body_fragment, variant)
        if extracted.footer_fragment:
            IntermediateParser._append_fragment(
                body, extracted.footer_fragment, variant
            )

    @staticmethod
    def _append_fragment(
        body: LexborNode, fragment_html: str, variant: TemplateVariant
    ) -> None:
        fragment = dom.parse_fragment(fragment_html)
        IntermediateParser._normalize_fragment(fragment, variant)

        for child in list(dom.children(fragment)):
            if dom.is_text(child):
                text = IntermediateParser._clean_text(dom.markup(child))
                if not text:
                    continue
                body.insert_child(IntermediateParser._new_paragraph(text))
                continue

            body.insert_child(dom.detach(child))

    @staticmethod
    def _append_text_lines(body: LexborNode, lines: list[str]) -> None:
        seen = set()
        for line in lines:
            text = IntermediateParser._clean_text(line)
            if not text or text in seen:
                continue
            seen.add(text)
            body.insert_child(IntermediateParser._new_paragraph(text))

    @staticmethod
    def _normalize_fragment(fragment: LexborNode, variant: TemplateVariant) -> None:
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
        fragment: LexborNode, variant: TemplateVariant
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
            for tag in dom.select(fragment, ".rkrubrik"):
                tag = dom.rename(tag, "h1")
                dom.set_attrs(tag, {})
        if config["wrapper_classes"]:
            IntermediateParser._unwrap_classed_wrappers(
                fragment,
                wrapper_classes=config["wrapper_classes"],
            )

    @staticmethod
    def _promote_known_ids(fragment: LexborNode) -> None:
        heading = dom.select_one(fragment, "#BrevInledandeText_Rubrik")
        if heading:
            heading = dom.rename(heading, "h1")
            dom.set_attrs(heading, {})

        for selector in [
            "#BrevInledandeText_Bilagor",
            "#BrevInledandeText_IngressText",
            "#BrevInledandeText_InledandeText",
            "#BrevFot_Beslut",
            "#BrevFot_Minister",
            "#BrevFot_Handlaeggare",
            "#BrevFot_KopiaTillText",
        ]:
            tag = dom.select_one(fragment, selector)
            if tag:
                tag = dom.rename(tag, "p")
                dom.set_attrs(tag, {})

    @staticmethod
    def _normalize_heading_tables(fragment: LexborNode) -> None:
        for table in list(dom.find_all(fragment, "table")):
            if dom.find(table, "table"):
                continue

            rows = dom.find_all(table, "tr", recursive=False)
            if not rows and dom.find(table, "tbody"):
                rows = dom.find_all(dom.find(table, "tbody"), "tr", recursive=False)

            if len(rows) != 1:
                continue

            cells = dom.find_all(rows[0], ["td", "th"], recursive=False)
            if not 1 <= len(cells) <= 2:
                continue

            texts = []
            heading_levels = []
            first_text = ""

            for index, cell in enumerate(cells):
                cell_text = IntermediateParser._clean_text(
                    dom.text(cell, " ", strip=True)
                )
                if not cell_text:
                    continue
                if index == 0:
                    first_text = cell_text
                texts.append(cell_text)

                for heading in dom.find_all(cell, re.compile("^h[1-6]$")):
                    heading_levels.append(int(heading.tag[1]))

                for descendant in dom.find_all(cell, True):
                    heading_levels.extend(
                        IntermediateParser._heading_levels_from_classes(
                            dom.get_attr(descendant, "class", [])
                        )
                    )

            if not texts:
                continue

            if len(texts) == 1:
                if not heading_levels:
                    continue
                level = min(heading_levels)
                heading = fragment.parser.create_node(f"h{level}")
                dom.set_text(heading, texts[0])
                table.replace_with(heading)
                continue

            if not heading_levels and not re.fullmatch(r"\d+(?:\.\d+)*", first_text):
                continue

            level = (
                min(heading_levels)
                if heading_levels
                else min(6, first_text.count(".") + 2)
            )

            heading = fragment.parser.create_node(f"h{level}")
            dom.set_text(heading, " ".join(texts))
            table.replace_with(heading)

    @staticmethod
    def _promote_classed_headings(fragment: LexborNode, pattern: str) -> None:
        regex = re.compile(pattern)
        for tag in list(dom.find_all(fragment, True)):
            if tag.tag in IntermediateParser.ALLOWED_TAGS:
                continue

            levels = []
            for class_name in dom.get_attr(tag, "class", []):
                match = regex.match(class_name)
                if match:
                    levels.append(min(6, int(match.group(1))))

            if not levels:
                continue

            if tag.parent and tag.parent.tag in {"td", "th"}:
                continue

            tag = dom.rename(tag, f"h{min(levels)}")
            dom.set_attrs(tag, {})

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
        fragment: LexborNode, wrapper_classes: set[str]
    ) -> None:
        for tag in list(dom.find_all(fragment, True)):
            if tag.tag in IntermediateParser.ALLOWED_TAGS:
                continue

            classes = set(dom.get_attr(tag, "class", []))
            if classes & wrapper_classes:
                tag.unwrap()

    @staticmethod
    def _promote_textual_blocks(fragment: LexborNode) -> None:
        for tag in list(dom.find_all(fragment, True)):
            if tag.tag in IntermediateParser.ALLOWED_TAGS:
                continue

            if tag.tag in {"script", "style", "img", "hr"}:
                tag.decompose()
                continue

            if tag.parent and tag.parent.tag in {
                "a",
                "em",
                "h1",
                "h2",
                "h3",
                "h4",
                "h5",
                "h6",
                "li",
                "p",
                "strong",
                "sup",
                "td",
                "th",
            }:
                tag.unwrap()
                continue

            has_block_child = any(
                dom.is_tag(child) and child.tag in IntermediateParser.BLOCK_TAGS
                for child in dom.children(tag)
            )

            text = IntermediateParser._clean_text(dom.text(tag, " ", strip=True))
            if has_block_child:
                tag.unwrap()
            elif text:
                tag = dom.rename(tag, "p")
                dom.set_attrs(tag, {})
            else:
                tag.decompose()

    @staticmethod
    def _sanitize_document(document: LexborNode) -> None:
        IntermediateParser._remove_comments(document)
        IntermediateParser._remove_noise(document)
        IntermediateParser._unwrap_layout_tables(document)

        for tag in list(dom.find_all(document, True)):
            if tag.tag not in IntermediateParser.ALLOWED_TAGS:
                tag.unwrap()
                continue

            if tag.tag == "a":
                href = dom.get_attr(tag, "href")
                dom.set_attrs(tag, {"href": href} if href else {})
            elif tag.tag == "table":
                attrs = {}
                tag_class = dom.get_attr(tag, "class")
                normalized_class = IntermediateParser._semantic_class_value(tag_class)
                if normalized_class:
                    attrs["class"] = normalized_class
                dom.set_attrs(tag, attrs)
            elif tag.tag == "td":
                attrs = {}
                tag_class = dom.get_attr(tag, "class")
                normalized_class = IntermediateParser._semantic_class_value(tag_class)
                if normalized_class:
                    attrs["class"] = normalized_class
                for attr_name in ("rowspan", "colspan"):
                    attr_value = dom.get_attr(tag, attr_name)
                    if attr_value:
                        attrs[attr_name] = attr_value
                dom.set_attrs(tag, attrs)
            elif tag.tag == "th":
                attrs = {}
                for attr_name in ("rowspan", "colspan", "scope"):
                    attr_value = dom.get_attr(tag, attr_name)
                    if attr_value:
                        attrs[attr_name] = attr_value
                dom.set_attrs(tag, attrs)
            elif tag.tag in {"h1", "p"}:
                attrs = {}
                tag_class = dom.get_attr(tag, "class")
                normalized_class = IntermediateParser._semantic_class_value(tag_class)
                if normalized_class:
                    attrs["class"] = normalized_class
                dom.set_attrs(tag, attrs)
            else:
                dom.set_attrs(tag, {})

        IntermediateParser._wrap_loose_text(dom.find(document, "body"))
        IntermediateParser._normalize_heading_contents(document)
        IntermediateParser._unwrap_inline_block_containers(document)
        IntermediateParser._collapse_nested_emphasis(document)
        IntermediateParser._split_invalid_paragraphs(document)
        # Splitting repaired paragraphs can expose inline siblings at body level.
        IntermediateParser._wrap_orphan_inline_body_nodes(document)
        IntermediateParser._remove_body_level_breaks(document)
        IntermediateParser._collapse_redundant_breaks(document)
        IntermediateParser._normalize_whitespace_nodes(document)
        IntermediateParser._remove_empty_tags(document)

    @staticmethod
    def _unwrap_inline_block_containers(document: LexborNode) -> None:
        for tag in reversed(dom.find_all(document, ["a", "em", "strong", "sup"])):
            if any(
                descendant.tag in IntermediateParser.BLOCK_TAGS
                for descendant in dom.find_all(tag, True)
            ):
                tag.unwrap()

    @staticmethod
    def _collapse_nested_emphasis(document: LexborNode) -> None:
        for tag in reversed(dom.find_all(document, ["em", "strong"])):
            if tag.parent and tag.parent.tag == tag.tag:
                tag.unwrap()

    @staticmethod
    def _split_invalid_paragraphs(document: LexborNode) -> None:
        inline_tags = {"a", "br"}
        paragraph_blockers = IntermediateParser.BLOCK_TAGS

        for paragraph in reversed(list(dom.find_all(document, "p"))):
            if not any(
                dom.is_tag(child) and child.tag in paragraph_blockers
                for child in dom.children(paragraph)
            ):
                continue

            parent = paragraph.parent
            if not parent:
                continue

            insert_before = paragraph
            inline_buffer: list[LexborNode | str] = []

            def flush_inline_buffer() -> None:
                nonlocal insert_before
                if not inline_buffer:
                    return

                new_paragraph = document.parser.create_node("p")
                for node in inline_buffer:
                    new_paragraph.insert_child(dom.detach(node))
                insert_before.insert_before(new_paragraph)
                inline_buffer.clear()

            for child in list(dom.children(paragraph)):
                if dom.is_text(child):
                    if IntermediateParser._clean_text(dom.markup(child)):
                        inline_buffer.append(child)
                    else:
                        child = dom.detach(child)
                    continue

                if child.tag in inline_tags:
                    inline_buffer.append(child)
                    continue

                flush_inline_buffer()
                insert_before.insert_before(dom.detach(child))

            flush_inline_buffer()
            paragraph.decompose()

    @staticmethod
    def _normalize_whitespace_nodes(fragment: LexborNode | str) -> None:
        for child in list(dom.children(fragment)):
            if dom.is_text(child):
                text = dom.markup(child)
                if not text.strip():
                    child = dom.detach(child)
                    continue

                normalized = IntermediateParser._clean_text(text)
                if normalized != text:
                    child.replace_with(normalized)
                continue

            IntermediateParser._normalize_whitespace_nodes(child)

    @staticmethod
    def _wrap_loose_text(body: LexborNode) -> None:
        for child in list(dom.children(body)):
            if not dom.is_text(child):
                continue

            text = IntermediateParser._clean_text(dom.markup(child))
            if not text:
                child = dom.detach(child)
                continue

            child.replace_with(IntermediateParser._new_paragraph(text))

    @staticmethod
    def _remove_empty_tags(document: LexborNode) -> None:
        for tag in reversed(dom.find_all(document, True)):
            if tag.tag in {"br", "html", "body"}:
                continue

            # Blank cells keep the letterhead's two-column Markdown table aligned.
            if tag.tag == "td":
                table = tag.parent
                while table and table.tag != "table":
                    table = table.parent
                if table and "letterhead" in dom.get_attr(table, "class", []):
                    continue

            text = IntermediateParser._clean_text(dom.text(tag, " ", strip=True))
            if text:
                continue

            if dom.find(tag, True):
                continue

            tag.decompose()

    @staticmethod
    def _remove_comments(fragment: LexborNode) -> None:
        for comment in dom.comments(fragment):
            dom.detach(comment)

    @staticmethod
    def _remove_noise(fragment: LexborNode) -> None:
        for tag in dom.find_all(fragment, ["img", "script", "style"]):
            tag.decompose()

    @staticmethod
    def _unwrap_layout_tables(fragment: LexborNode | str) -> None:
        changed = True
        while changed:
            changed = False
            for table in list(dom.find_all(fragment, "table")):
                rows = IntermediateParser._table_rows(table)
                if len(rows) != 1:
                    continue

                cells = dom.find_all(rows[0], ["td", "th"], recursive=False)
                if len(cells) != 1:
                    continue

                cell = cells[0]
                if dom.get_attr(cell, "rowspan") or dom.get_attr(cell, "colspan"):
                    continue

                if not any(dom.is_tag(child) for child in dom.children(cell)):
                    continue

                for child in list(dom.children(cell)):
                    table.insert_before(dom.detach(child))
                table.decompose()
                changed = True
                break

    @staticmethod
    def _unwrap_tag_name(fragment: LexborNode, tag_name: str) -> None:
        for tag in dom.find_all(fragment, tag_name):
            tag.unwrap()

    @staticmethod
    def _strings_from_selector(source: LexborNode, selector: str) -> list[str]:
        items = []
        for tag in dom.select(source, selector):
            items.extend(IntermediateParser._strings_from_tag(tag))
        return items

    @staticmethod
    def _strings_from_tag(tag: LexborNode | None) -> list[str]:
        if not tag:
            return []
        return [
            IntermediateParser._clean_text(text)
            for text in dom.strings(tag)
            if IntermediateParser._clean_text(text)
        ]

    @staticmethod
    def _clean_text(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _new_paragraph(text: str) -> LexborNode:
        soup = dom.parse_html("")
        paragraph = soup.parser.create_node("p")
        dom.set_text(paragraph, text)
        return paragraph

    @staticmethod
    def _semantic_class_value(tag_class) -> str | None:
        class_names = (
            tag_class
            if isinstance(tag_class, list)
            else [tag_class]
            if tag_class
            else []
        )
        semantic = [
            class_name
            for class_name in class_names
            if class_name in IntermediateParser.SEMANTIC_CLASSES
        ]
        if not semantic:
            return None
        return " ".join(semantic)

    @staticmethod
    def _normalize_heading_contents(document: LexborNode) -> None:
        for heading in dom.find_all(document, re.compile("^h[1-6]$")):
            text = IntermediateParser._clean_text(dom.text(heading, " ", strip=True))
            if not text:
                continue

            if any(
                dom.is_tag(child) and child.tag in IntermediateParser.BLOCK_TAGS
                for child in dom.children(heading)
            ):
                dom.clear(heading)
                dom.set_text(heading, text)

    @staticmethod
    def _wrap_orphan_inline_body_nodes(document: LexborNode) -> None:
        body = dom.find(document, "body")
        if not body:
            return

        inline_tags = {"a", "em", "strong", "sup"}
        for child in list(dom.children(body)):
            if not dom.is_tag(child) or child.tag not in inline_tags:
                continue

            if any(
                descendant.tag in IntermediateParser.BLOCK_TAGS
                for descendant in dom.find_all(child, True)
            ):
                child.unwrap()
                continue

            paragraph = document.parser.create_node("p")
            paragraph = dom.insert_before(child, paragraph)
            paragraph.insert_child(dom.detach(child))

    @staticmethod
    def _remove_body_level_breaks(document: LexborNode) -> None:
        body = dom.find(document, "body")
        if not body:
            return

        for child in list(dom.children(body)):
            if dom.is_tag(child) and child.tag == "br":
                child.decompose()

    @staticmethod
    def _collapse_redundant_breaks(fragment: LexborNode | str) -> None:
        for parent in dom.find_all(fragment, True):
            previous_was_br = False
            for child in list(dom.children(parent)):
                if dom.is_tag(child) and child.tag == "br":
                    if previous_was_br:
                        child.decompose()
                        continue
                    previous_was_br = True
                    continue

                if dom.is_text(child) and not IntermediateParser._clean_text(
                    dom.markup(child)
                ):
                    child = dom.detach(child)
                    continue

                previous_was_br = False

    @staticmethod
    def _normalize_label_paragraphs(document: LexborNode) -> None:
        body = dom.find(document, "body")
        if not body:
            return

        for paragraph in dom.find_all(body, "p", recursive=False):
            if dom.find(paragraph, "strong", recursive=False):
                continue

            if any(
                dom.is_tag(child) and child.tag != "br"
                for child in dom.children(paragraph)
            ):
                continue

            text = IntermediateParser._clean_text(dom.text(paragraph, " ", strip=True))
            if not text:
                continue

            if not (
                XHTMLOutlineNormalizer._is_label_heading(text)
                or XHTMLOutlineNormalizer._is_local_numbered_label(text)
            ):
                continue

            strong = document.parser.create_node("strong")
            dom.set_text(strong, text)
            dom.clear(paragraph)
            paragraph.insert_child(strong)

    @staticmethod
    def _normalize_policy_outline_blocks(document: LexborNode) -> None:
        body = dom.find(document, "body")
        if not body:
            return

        children = list(dom.find_all(body, recursive=False))
        index = 0
        while index < len(children):
            child = children[index]
            if child.tag != "p":
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
                children = list(dom.find_all(body, recursive=False))
                index += len(new_nodes)
                continue

            sequence = [child]
            next_index = index + 1
            while next_index < len(children):
                sibling = children[next_index]
                if sibling.tag == "br":
                    sequence.append(sibling)
                    next_index += 1
                    continue
                if sibling.tag == "p":
                    sibling_fragments = (
                        IntermediateParser._policy_outline_fragments_from_tag(sibling)
                    )
                    pending_role = IntermediateParser._policy_outline_pending_role(
                        sequence
                    )
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
                children = list(dom.find_all(body, recursive=False))
                index += len(new_nodes)
                continue

            index = next_index

    @staticmethod
    def _policy_outline_fragments_from_tag(tag: LexborNode) -> list[str]:
        if tag.tag != "p":
            return []

        text = dom.text(tag, "\n", strip=True)
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
    def _parse_policy_outline_lines(
        sequence: list[LexborNode],
    ) -> list[tuple[str, str]]:
        fragments = []
        for node in sequence:
            if node.tag != "p":
                continue
            fragments.extend(
                IntermediateParser._policy_outline_fragments_from_tag(node)
            )

        values, _ = IntermediateParser._policy_outline_state_from_fragments(fragments)
        lines = []
        for role in ["PO", "VO", "VG"]:
            value = values.get(role, "").strip()
            if value:
                lines.append((role, value))
        return lines

    @staticmethod
    def _policy_outline_pending_role(sequence: list[LexborNode]) -> str | None:
        fragments = []
        for node in sequence:
            if node.tag != "p":
                continue
            fragments.extend(
                IntermediateParser._policy_outline_fragments_from_tag(node)
            )

        _, pending_role = IntermediateParser._policy_outline_state_from_fragments(
            fragments
        )
        return pending_role

    @staticmethod
    def _policy_outline_has_any_role(sequence: list[LexborNode]) -> bool:
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
                values[current_role] = (
                    f"{existing} {normalized}".strip() if existing else normalized
                )

        pending_role = (
            current_role
            if current_role in {"VO", "VG"} and not values.get(current_role, "").strip()
            else None
        )
        return values, pending_role

    @staticmethod
    def _new_policy_outline_paragraph(
        document: LexborNode, line: tuple[str, str]
    ) -> LexborNode:
        role, value = line
        paragraph = document.parser.create_node("p")

        if role == "PO":
            strong = document.parser.create_node("strong")
            dom.set_text(strong, f"{role} {value}")
            paragraph.insert_child(strong)
            return paragraph

        if role == "VO":
            strong = document.parser.create_node("strong")
            emphasis = document.parser.create_node("em")
            dom.set_text(emphasis, f"{role} {value}")
            strong.insert_child(emphasis)
            paragraph.insert_child(strong)
            return paragraph

        emphasis = document.parser.create_node("em")
        dom.set_text(emphasis, f"{role} {value}")
        paragraph.insert_child(emphasis)
        return paragraph

    @staticmethod
    def _normalize_footer_signature_tables(document: LexborNode) -> None:
        body = dom.find(document, "body")
        if not body:
            return

        children = list(dom.find_all(body, recursive=False))
        for index, child in enumerate(children[:-1]):
            if child.tag != "p":
                continue

            text = IntermediateParser._clean_text(dom.text(child, " ", strip=True))
            if text != "På regeringens vägnar":
                continue

            table = children[index + 1]
            if not IntermediateParser._is_simple_signature_table(table):
                continue

            paragraphs = []
            for row in IntermediateParser._table_rows(table):
                cell = dom.find(row, ["td", "th"], recursive=False)
                if not cell:
                    continue
                cell_text = IntermediateParser._clean_text(
                    dom.text(cell, " ", strip=True)
                )
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
    def _is_simple_signature_table(tag: LexborNode) -> bool:
        if tag.tag != "table":
            return False

        rows = IntermediateParser._table_rows(tag)
        if not rows:
            return False

        for row in rows:
            cells = dom.find_all(row, ["td", "th"], recursive=False)
            if len(cells) != 1:
                return False

            cell = cells[0]
            if dom.get_attr(cell, "rowspan") or dom.get_attr(cell, "colspan"):
                return False

            if any(
                dom.is_tag(desc) and desc.tag not in {"br"}
                for desc in dom.find_all(cell, True)
            ):
                return False

        return True

    @staticmethod
    def _preserve_italic_semantics(fragment: LexborNode) -> None:
        for tag in dom.find_all(fragment, True):
            classes = set(dom.get_attr(tag, "class", []))
            if "italic" not in classes:
                continue

            has_em_child = any(
                dom.is_tag(child) and child.tag == "em" for child in dom.children(tag)
            )
            if has_em_child:
                continue

            text = IntermediateParser._clean_text(dom.text(tag, " ", strip=True))
            if not text:
                continue

            dom.clear(tag)
            emphasis = fragment.parser.create_node("em")
            dom.set_text(emphasis, text)
            tag.insert_child(emphasis)

    @staticmethod
    def _promote_footnotes(fragment: LexborNode) -> None:
        for tag in list(dom.find_all(fragment, True)):
            classes = set(dom.get_attr(tag, "class", []))
            if "fotnot" not in classes:
                continue

            lines = IntermediateParser._extract_footnote_lines(tag)
            if not lines:
                tag.decompose()
                continue

            paragraphs = []
            for line in lines:
                paragraph = fragment.parser.create_node("p")
                emphasis = fragment.parser.create_node("em")
                for node in line:
                    emphasis.insert_child(node)
                paragraph.insert_child(emphasis)
                paragraphs.append(paragraph)

            replacement = paragraphs[0]
            current = dom.replace(tag, replacement)
            for paragraph in paragraphs[1:]:
                current = dom.insert_after(current, paragraph)

    @staticmethod
    def _extract_footnote_lines(tag: LexborNode) -> list[list[LexborNode | str]]:
        lines: list[list[LexborNode | str]] = [[]]

        for child in list(dom.children(tag)):
            if dom.is_tag(child) and child.tag == "br":
                if lines[-1]:
                    lines.append([])
                child = dom.detach(child)
                continue

            if dom.is_text(child):
                text = IntermediateParser._clean_text(dom.markup(child))
                child = dom.detach(child)
                if not text:
                    continue
                node = str(text)
                if (
                    lines[-1]
                    and dom.is_tag(lines[-1][-1])
                    and lines[-1][-1].tag == "sup"
                ):
                    lines[-1].append(str(f" {text}"))
                else:
                    lines[-1].append(node)
                continue

            child = dom.detach(child)
            dom.set_attrs(child, {})
            lines[-1].append(child)

        return [
            line
            for line in lines
            if any(IntermediateParser._clean_text(dom.markup(node)) for node in line)
        ]

    @staticmethod
    def _normalize_anslag_summary_tables(document: LexborNode) -> None:
        body = dom.find(document, "body")
        if not body:
            return

        children = list(dom.find_all(body, recursive=False))
        i = 0

        while i < len(children):
            tag = children[i]
            if not IntermediateParser._is_tilldelade_anslag_heading(tag):
                i += 1
                continue

            current_level = int(tag.tag[1])
            j = i + 1
            while j < len(children):
                next_tag = children[j]
                if IntermediateParser._is_heading(next_tag):
                    next_level = int(next_tag.tag[1])
                    if next_level <= current_level:
                        break
                j += 1

            region = children[i + 1 : j]
            IntermediateParser._normalize_anslag_region(document, region)
            children = list(dom.find_all(body, recursive=False))
            i = j

    @staticmethod
    def _normalize_anslag_region(
        document: LexborNode, region: list[LexborNode]
    ) -> None:
        i = 0
        while i < len(region):
            tag = region[i]
            if IntermediateParser._is_anslag_title_paragraph(tag):
                title_paragraph, normalized_table, consumed = (
                    IntermediateParser._build_anslag_table_from_sequence(
                        document,
                        tag,
                        region,
                        i,
                    )
                )
                if normalized_table:
                    title_paragraph = dom.replace(tag, title_paragraph)
                    dom.insert_after(title_paragraph, normalized_table)
                    for sibling in region[i + 1 : i + consumed]:
                        sibling.decompose()
                    i += consumed
                    continue

            if IntermediateParser._is_anslag_title_table(tag):
                title_paragraph, normalized_table, consumed = (
                    IntermediateParser._build_anslag_table_from_sequence(
                        document,
                        tag,
                        region,
                        i,
                    )
                )
                if normalized_table:
                    title_paragraph = dom.replace(tag, title_paragraph)
                    dom.insert_after(title_paragraph, normalized_table)
                    for sibling in region[i + 1 : i + consumed]:
                        sibling.decompose()
                    i += consumed
                    continue

            if IntermediateParser._is_combined_anslag_table(tag):
                title_paragraph, normalized_table = (
                    IntermediateParser._build_anslag_table_from_combined_table(
                        document,
                        tag,
                    )
                )
                if normalized_table and title_paragraph:
                    title_paragraph = dom.replace(tag, title_paragraph)
                    dom.insert_after(title_paragraph, normalized_table)

            i += 1

    @staticmethod
    def _build_anslag_table_from_sequence(
        document: LexborNode,
        title_tag: LexborNode,
        region: list[LexborNode],
        start_index: int,
    ) -> tuple[LexborNode | None, LexborNode | None, int]:
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
            IntermediateParser._build_merged_anslag_table(
                document, ap_header, table_rows
            ),
            consumed,
        )

    @staticmethod
    def _build_anslag_table_from_combined_table(
        document: LexborNode, table: LexborNode
    ) -> tuple[LexborNode | None, LexborNode | None]:
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
        document: LexborNode, ap_header: list[str] | None, rows: list[tuple]
    ) -> LexborNode:
        table = document.parser.create_node("table")
        tbody = document.parser.create_node("tbody")
        tbody = dom.append(table, tbody)

        if ap_header:
            header_row = document.parser.create_node("tr")
            for label in ap_header:
                th = document.parser.create_node("th")
                dom.set_text(th, label)
                header_row.insert_child(th)
            tbody.insert_child(header_row)

        for row_data in rows:
            kind = row_data[0]
            tr = document.parser.create_node("tr")
            if kind == "disposition":
                left = document.parser.create_node("td")
                dom.set_attr(left, "colspan", "2")
                dom.set_text(left, row_data[1])
                amount = document.parser.create_node("td")
                dom.set_text(amount, row_data[2])
                tr.insert_child(left)
                tr.insert_child(amount)
            elif kind == "ap":
                for value in row_data[1:]:
                    td = document.parser.create_node("td")
                    dom.set_text(td, value)
                    tr.insert_child(td)
            tbody.insert_child(tr)

        return table

    @staticmethod
    def _is_tilldelade_anslag_heading(tag: LexborNode) -> bool:
        return IntermediateParser._is_heading(tag) and "tilldelade anslag" in (
            IntermediateParser._clean_text(dom.text(tag, " ", strip=True)).lower()
        )

    @staticmethod
    def _is_heading(tag: LexborNode) -> bool:
        return tag.tag in {"h1", "h2", "h3", "h4", "h5", "h6"}

    @staticmethod
    def _is_anslag_title_paragraph(tag: LexborNode) -> bool:
        if tag.tag != "p":
            return False
        strong = dom.find(tag, "strong", recursive=False)
        if not strong:
            return False
        text = IntermediateParser._clean_text(dom.text(strong, " ", strip=True))
        return bool(re.match(r"^\d+:\d+\s", text))

    @staticmethod
    def _is_anslag_title_table(tag: LexborNode) -> bool:
        if tag.tag != "table":
            return False
        rows = IntermediateParser._table_rows(tag)
        if len(rows) != 1:
            return False
        cells = dom.find_all(rows[0], ["td", "th"], recursive=False)
        if len(cells) != 2:
            return False
        first = IntermediateParser._clean_text(dom.text(cells[0], " ", strip=True))
        second = IntermediateParser._clean_text(dom.text(cells[1], " ", strip=True))
        return bool(
            re.fullmatch(r"\d+:\d+", first)
            and second
            and not second.startswith("Disponeras av")
        )

    @staticmethod
    def _is_combined_anslag_table(tag: LexborNode) -> bool:
        if tag.tag != "table":
            return False
        text = IntermediateParser._clean_text(dom.text(tag, " ", strip=True))
        return "Disponeras av" in text and bool(re.search(r"\bap\.\d+", text))

    @staticmethod
    def _is_anslag_disposition_table(tag: LexborNode) -> bool:
        if tag.tag != "table":
            return False
        rows = IntermediateParser._table_rows(tag)
        if not rows:
            return False
        first_row = rows[0]
        first_cell = dom.find(first_row, ["td", "th"], recursive=False)
        if not first_cell:
            return False
        text = IntermediateParser._clean_text(dom.text(first_cell, " ", strip=True))
        return text.startswith("Disponeras av")

    @staticmethod
    def _is_anslag_ap_table(tag: LexborNode) -> bool:
        if tag.tag != "table":
            return False
        return bool(IntermediateParser._parse_ap_rows(tag))

    @staticmethod
    def _parse_anslag_title(tag: LexborNode) -> tuple[str, str]:
        if tag.tag == "p":
            text = IntermediateParser._clean_text(dom.text(tag, " ", strip=True))
            match = re.match(r"^(\d+:\d+)\s+(.+)$", text)
            if match:
                return match.group(1), match.group(2)
            return "", ""

        rows = IntermediateParser._table_rows(tag)
        if not rows:
            return "", ""
        row = rows[0]
        cells = dom.find_all(row, ["td", "th"], recursive=False)
        if len(cells) != 2:
            return "", ""
        return (
            IntermediateParser._clean_text(dom.text(cells[0], " ", strip=True)),
            IntermediateParser._clean_text(dom.text(cells[1], " ", strip=True)),
        )

    @staticmethod
    def _parse_disposition_row(tag: LexborNode) -> tuple[str, str] | None:
        rows = IntermediateParser._table_rows(tag)
        if not rows:
            return None
        row = rows[0]
        cells = [
            IntermediateParser._clean_text(dom.text(cell, " ", strip=True))
            for cell in dom.find_all(row, ["td", "th"], recursive=False)
        ]
        cells = [cell for cell in cells if cell]
        if not cells or not cells[0].startswith("Disponeras av"):
            return None
        return cells[0], cells[-1] if len(cells) > 1 else ""

    @staticmethod
    def _parse_ap_rows(
        tag: LexborNode,
    ) -> tuple[list[str] | None, list[tuple[str, str, str, str]]]:
        header = None
        rows = []
        for index, row in enumerate(IntermediateParser._table_rows(tag)):
            cells = [
                IntermediateParser._clean_text(dom.text(cell, " ", strip=True))
                for cell in dom.find_all(row, ["td", "th"], recursive=False)
            ]
            cells = [cell for cell in cells if cell]
            if not cells:
                continue
            if index == 0 and not re.fullmatch(
                r"(?:\d+:\d+\s+)?ap\.\d+(?:\.\d+)?", cells[0]
            ):
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
        tag: LexborNode,
        initial_disposition: str,
        initial_disposition_amount: str,
    ) -> tuple[list[str] | None, list[tuple]]:
        rows = []
        current_disposition = initial_disposition
        current_disposition_amount = initial_disposition_amount
        header = None

        for index, row in enumerate(IntermediateParser._table_rows(tag)):
            cells = [
                IntermediateParser._clean_text(dom.text(cell, " ", strip=True))
                for cell in dom.find_all(row, ["td", "th"], recursive=False)
            ]
            cells = [cell for cell in cells if cell]
            if not cells:
                continue

            if (
                index == 0
                and len(cells) >= 3
                and cells[0].lower() in {"nomenklatur", "anslag/ap", "anslag/ap/dp"}
            ):
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
    def _build_disposition_table_row(
        disposition: str, amount: str
    ) -> tuple[str, str, str]:
        return ("disposition", disposition, amount)

    @staticmethod
    def _build_anslag_title_paragraph(document: LexborNode, text: str) -> LexborNode:
        paragraph = document.parser.create_node("p")
        strong = document.parser.create_node("strong")
        dom.set_text(strong, text)
        paragraph.insert_child(strong)
        return paragraph

    @staticmethod
    def _table_rows(table: LexborNode) -> list[LexborNode]:
        rows = dom.find_all(table, "tr", recursive=False)
        if rows:
            return rows

        for section_name in ("thead", "tbody"):
            section = dom.find(table, section_name, recursive=False)
            if section:
                rows.extend(dom.find_all(section, "tr", recursive=False))

        return rows
