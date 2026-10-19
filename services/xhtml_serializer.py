import html

from selectolax.lexbor import LexborNode

from services import html_dom as dom


class XHTMLSerializer(object):
    BLOCK_TAGS = {"html", "body", "table", "thead", "tbody", "tr", "ul", "ol"}
    INLINE_CHILD_TAGS = {"a", "br", "em", "strong", "sup"}

    @staticmethod
    def serialize_document(document: LexborNode, clean_text) -> str:
        html_tag = dom.find(document, "html")
        if not html_tag:
            return "<html>\n  <body></body>\n</html>\n"

        lines = XHTMLSerializer._serialize_tag(html_tag, level=0, clean_text=clean_text)
        return "\n".join(lines) + "\n"

    @staticmethod
    def _serialize_tag(tag: LexborNode, level: int, clean_text) -> list[str]:
        indent = "  " * level
        attrs = XHTMLSerializer._serialize_attrs(tag)

        if tag.tag == "br":
            return [f"{indent}<br/>"]

        if XHTMLSerializer._should_inline_tag(tag):
            content = XHTMLSerializer._serialize_inline_children(tag, clean_text)
            return [f"{indent}<{tag.tag}{attrs}>{content}</{tag.tag}>"]

        lines = [f"{indent}<{tag.tag}{attrs}>"]
        for child in dom.children(tag):
            if dom.is_text(child):
                text = clean_text(dom.markup(child))
                if text:
                    lines.append(f"{'  ' * (level + 1)}{html.escape(text)}")
                continue

            lines.extend(XHTMLSerializer._serialize_tag(child, level + 1, clean_text))

        lines.append(f"{indent}</{tag.tag}>")
        return lines

    @staticmethod
    def _serialize_attrs(tag: LexborNode) -> str:
        if tag.tag == "a":
            allowed_attr_names = ["href"]
        elif tag.tag == "table":
            allowed_attr_names = ["class"]
        elif tag.tag == "td":
            allowed_attr_names = ["class", "rowspan", "colspan"]
        elif tag.tag == "th":
            allowed_attr_names = ["rowspan", "colspan", "scope"]
        elif tag.tag in {"h1", "p"}:
            allowed_attr_names = ["class"]
        else:
            allowed_attr_names = []

        parts = []
        for attr_name in allowed_attr_names:
            attr_value = tag.attributes.get(attr_name)
            if attr_value:
                parts.append(
                    f' {attr_name}="{html.escape(dom.markup(attr_value), quote=True)}"'
                )

        return "".join(parts)

    @staticmethod
    def _should_inline_tag(tag: LexborNode) -> bool:
        if tag.tag in XHTMLSerializer.BLOCK_TAGS:
            return False

        return not any(
            dom.is_tag(child) and child.tag not in XHTMLSerializer.INLINE_CHILD_TAGS
            for child in dom.children(tag)
        )

    @staticmethod
    def _serialize_inline_children(tag: LexborNode, clean_text) -> str:
        parts = []
        for child in dom.children(tag):
            if dom.is_text(child):
                text = clean_text(dom.markup(child))
                if text:
                    parts.append(html.escape(text))
                continue

            if child.tag == "br":
                parts.append("<br/>")
                continue

            parts.extend(
                XHTMLSerializer._serialize_tag(child, level=0, clean_text=clean_text)
            )

        return "".join(parts)
