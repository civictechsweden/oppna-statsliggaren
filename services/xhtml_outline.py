import re

from bs4 import BeautifulSoup, Tag


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
    def normalize(document: BeautifulSoup, clean_text) -> None:
        body = document.body
        if not body:
            return

        XHTMLOutlineNormalizer._merge_split_sibling_headings(body, clean_text)

        headings = list(body.find_all(re.compile(r"^h[1-6]$"), recursive=False))
        if not headings:
            return

        headings[0].name = "h1"
        headings[0]["class"] = "document-title"

        for heading in headings[1:]:
            text = clean_text(heading.get_text(" ", strip=True))
            if not text:
                continue

            if XHTMLOutlineNormalizer._is_label_heading(text):
                XHTMLOutlineNormalizer._replace_heading_with_strong_paragraph(
                    heading, clean_text
                )
                continue

            major_division = XHTMLOutlineNormalizer._normalize_major_division_title(text)
            if major_division:
                heading.name = "h2"
                heading.string = major_division
                continue

            if XHTMLOutlineNormalizer._is_local_numbered_label(text):
                XHTMLOutlineNormalizer._replace_heading_with_strong_paragraph(
                    heading, clean_text
                )
                continue

            numbered_level = XHTMLOutlineNormalizer._numbered_outline_level(text)
            if numbered_level is not None:
                heading.name = f"h{numbered_level}"
                continue

            XHTMLOutlineNormalizer._replace_heading_with_strong_paragraph(
                heading, clean_text
            )

    @staticmethod
    def _merge_split_sibling_headings(body: Tag, clean_text) -> None:
        changed = True
        while changed:
            changed = False
            headings = list(body.find_all(re.compile(r"^h[1-6]$"), recursive=False))
            for first, second in zip(headings, headings[1:]):
                if first.find_next_sibling() is not second:
                    continue

                first_text = clean_text(first.get_text(" ", strip=True))
                second_text = clean_text(second.get_text(" ", strip=True))
                if not (
                    XHTMLOutlineNormalizer._is_split_heading_prefix(first_text)
                    and second_text
                ):
                    continue

                first.string = f"{first_text} {second_text}"
                second.decompose()
                changed = True
                break

    @staticmethod
    def _is_split_heading_prefix(text: str) -> bool:
        return bool(
            re.fullmatch(r"\d+(?:\.\d+)*", text)
            or re.fullmatch(r"\d+:\d+", text)
        )

    @staticmethod
    def _is_label_heading(text: str) -> bool:
        normalized = text.lower()
        if normalized in XHTMLOutlineNormalizer.LABEL_HEADINGS:
            return True

        return bool(
            re.fullmatch(r"mål(?: \d+)?", normalized)
            or normalized.startswith("mål - ")
        )

    @staticmethod
    def _is_local_numbered_label(text: str) -> bool:
        return bool(re.match(r"^\d+\.\s+\S", text))

    @staticmethod
    def _replace_heading_with_strong_paragraph(heading: Tag, clean_text) -> None:
        soup = BeautifulSoup("", "html.parser")
        paragraph = soup.new_tag("p")
        strong = soup.new_tag("strong")

        if any(isinstance(child, Tag) and child.name == "em" for child in heading.contents):
            for child in list(heading.contents):
                strong.append(child.extract())
        else:
            strong.string = clean_text(heading.get_text(" ", strip=True))

        paragraph.append(strong)
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
