import re

from selectolax.lexbor import LexborNode

from services import html_dom as dom
from services.heading_alignment import align_headings


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

        align_headings(document, clean_text)

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
    def _normalize_major_division_title(text: str) -> str | None:
        normalized = re.sub(r"^\d+(?:\.\d+)?\s+", "", text.strip())
        return XHTMLOutlineNormalizer.MAJOR_DIVISION_TITLES.get(normalized.lower())

    @staticmethod
    def _numbered_outline_level(text: str) -> int | None:
        match = re.match(r"^(\d+(?:\.\d+)*)\s+\S", text)
        if match:
            return min(6, len(match.group(1).split(".")) + 2)

        return None
