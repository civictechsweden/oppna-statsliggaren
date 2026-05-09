import html

from bs4 import BeautifulSoup, NavigableString, Tag


class XHTMLSerializer(object):
    BLOCK_TAGS = {"html", "body", "table", "thead", "tbody", "tr", "ul", "ol"}

    @staticmethod
    def serialize_document(document: BeautifulSoup, clean_text) -> str:
        html_tag = document.html
        if not html_tag:
            return "<html>\n  <body></body>\n</html>\n"

        lines = XHTMLSerializer._serialize_tag(html_tag, level=0, clean_text=clean_text)
        return "\n".join(lines) + "\n"

    @staticmethod
    def _serialize_tag(tag: Tag, level: int, clean_text) -> list[str]:
        indent = "  " * level
        attrs = XHTMLSerializer._serialize_attrs(tag)

        if tag.name == "br":
            return [f"{indent}<br/>"]

        if XHTMLSerializer._should_inline_tag(tag):
            content = XHTMLSerializer._serialize_inline_children(tag, clean_text)
            return [f"{indent}<{tag.name}{attrs}>{content}</{tag.name}>"]

        lines = [f"{indent}<{tag.name}{attrs}>"]
        for child in tag.children:
            if isinstance(child, NavigableString):
                text = clean_text(str(child))
                if text:
                    lines.append(f'{"  " * (level + 1)}{html.escape(text)}')
                continue

            lines.extend(
                XHTMLSerializer._serialize_tag(child, level + 1, clean_text)
            )

        lines.append(f"{indent}</{tag.name}>")
        return lines

    @staticmethod
    def _serialize_attrs(tag: Tag) -> str:
        if tag.name == "a":
            allowed_attr_names = ["href"]
        elif tag.name == "td":
            allowed_attr_names = ["rowspan", "colspan"]
        elif tag.name == "th":
            allowed_attr_names = ["rowspan", "colspan", "scope"]
        else:
            allowed_attr_names = []

        parts = []
        for attr_name in allowed_attr_names:
            attr_value = tag.get(attr_name)
            if attr_value:
                parts.append(
                    f' {attr_name}="{html.escape(str(attr_value), quote=True)}"'
                )

        return "".join(parts)

    @staticmethod
    def _should_inline_tag(tag: Tag) -> bool:
        if tag.name in XHTMLSerializer.BLOCK_TAGS:
            return False

        return not any(
            isinstance(child, Tag) and child.name != "br" for child in tag.children
        )

    @staticmethod
    def _serialize_inline_children(tag: Tag, clean_text) -> str:
        parts = []
        for child in tag.children:
            if isinstance(child, NavigableString):
                text = clean_text(str(child))
                if text:
                    parts.append(html.escape(text))
                continue

            if child.name == "br":
                parts.append("<br/>")
                continue

            parts.extend(XHTMLSerializer._serialize_tag(child, level=0, clean_text=clean_text))

        return "".join(parts)
