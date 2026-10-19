import re

from selectolax.lexbor import LexborNode

from services import html_dom as dom


class XHTMLOutlineNormalizer(object):
    LABEL_HEADINGS = {
        "kopia till",
        "mål",
        "återrapportering",
        "återrrapportering",
        "villkor",
    }

    MAJOR_DIVISION_TITLES = {
        "verksamhet": "VERKSAMHET",
        "finansiering": "FINANSIERING",
        "avgifter och bidrag": "AVGIFTER OCH BIDRAG",
        "undantag från ekonomiadministrativa regelverket": (
            "UNDANTAG FRÅN EKONOMIADMINISTRATIVA REGELVERKET"
        ),
    }

    @staticmethod
    def normalize(document: LexborNode, clean_text) -> None:
        body = dom.find(document, "body")
        if not body:
            return

        XHTMLOutlineNormalizer._merge_split_sibling_headings(body, clean_text)

        headings = list(dom.find_all(body, re.compile("^h[1-6]$"), recursive=False))
        if not headings:
            return

        headings[0] = dom.rename(headings[0], "h1")
        dom.set_attr(headings[0], "class", "document-title")

        for heading in headings[1:]:
            text = clean_text(dom.text(heading, " ", strip=True))
            if not text:
                continue

            if XHTMLOutlineNormalizer._is_label_heading(text):
                XHTMLOutlineNormalizer._replace_heading_with_strong_paragraph(
                    heading, clean_text
                )
                continue

            major_division = XHTMLOutlineNormalizer._normalize_major_division_title(
                text
            )
            if major_division:
                heading = dom.rename(heading, "h2")
                dom.set_text(heading, major_division)
                continue

            if XHTMLOutlineNormalizer._is_local_numbered_label(text):
                XHTMLOutlineNormalizer._replace_heading_with_strong_paragraph(
                    heading, clean_text
                )
                continue

            numbered_level = XHTMLOutlineNormalizer._numbered_outline_level(text)
            if numbered_level is not None:
                heading = dom.rename(heading, f"h{numbered_level}")
                continue

            XHTMLOutlineNormalizer._replace_heading_with_strong_paragraph(
                heading, clean_text
            )

    @staticmethod
    def _merge_split_sibling_headings(body: LexborNode, clean_text) -> None:
        changed = True
        while changed:
            changed = False
            headings = list(dom.find_all(body, re.compile("^h[1-6]$"), recursive=False))
            for first, second in zip(headings, headings[1:]):
                if dom.next_sibling(first) != second:
                    continue

                first_text = clean_text(dom.text(first, " ", strip=True))
                second_text = clean_text(dom.text(second, " ", strip=True))
                if not (
                    XHTMLOutlineNormalizer._is_split_heading_prefix(first_text)
                    and second_text
                ):
                    continue

                dom.set_text(first, f"{first_text} {second_text}")
                second.decompose()
                changed = True
                break

    @staticmethod
    def _is_split_heading_prefix(text: str) -> bool:
        return bool(
            re.fullmatch(r"\d+(?:\.\d+)*", text) or re.fullmatch(r"\d+:\d+", text)
        )

    @staticmethod
    def _is_label_heading(text: str) -> bool:
        normalized = text.lower()
        if normalized in XHTMLOutlineNormalizer.LABEL_HEADINGS:
            return True

        return bool(
            re.fullmatch(r"mål(?: \d+)?", normalized) or normalized.startswith("mål - ")
        )

    @staticmethod
    def _is_local_numbered_label(text: str) -> bool:
        return bool(re.match(r"^\d+\.\s+\S", text))

    @staticmethod
    def _replace_heading_with_strong_paragraph(heading: LexborNode, clean_text) -> None:
        soup = dom.parse_html("")
        paragraph = soup.parser.create_node("p")
        strong = soup.parser.create_node("strong")

        if any(
            dom.is_tag(child) and child.tag == "em" for child in dom.children(heading)
        ):
            for child in list(dom.children(heading)):
                strong.insert_child(dom.detach(child))
        else:
            dom.set_text(strong, clean_text(dom.text(heading, " ", strip=True)))

        paragraph.insert_child(strong)
        heading.replace_with(paragraph)

    @staticmethod
    def _normalize_major_division_title(text: str) -> str | None:
        normalized = re.sub(r"^\d+(?:\.\d+)?\s+", "", text.strip())
        return XHTMLOutlineNormalizer.MAJOR_DIVISION_TITLES.get(normalized.lower())

    @staticmethod
    def _numbered_outline_level(text: str) -> int | None:
        match = re.match(r"^(\d+(?:\.\d+)*)\s+\S", text)
        if match:
            return min(6, len(match.group(1).split(".")) + 2)

        if re.match(r"^\d+\.\s+\S", text):
            return 4

        return None
