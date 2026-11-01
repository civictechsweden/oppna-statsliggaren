import html
import json
import re

from bs4 import BeautifulSoup, SoupStrainer
from selectolax.lexbor import LexborHTMLParser


class Parser(object):
    @staticmethod
    def parse_latest_remote_rbid(response) -> int:
        html_text = html.unescape(response.text)

        return max(int(value) for value in re.findall(r"rbid=(\d+)", html_text, re.IGNORECASE))

    @staticmethod
    def parse_metadata(response, rbid: int):
        html_text = html.unescape(response.text)
        title = Parser._extract_title(html_text)
        normalized_title = Parser._normalize_whitespace(
            title.removesuffix(" - Statskontoret")
        )
        fail = Parser._is_missing_letter_page(response, html_text, normalized_title)

        metadata = {}
        metadata["rbid"] = rbid
        metadata["type"] = None
        metadata["date"] = None
        metadata["year"] = None
        metadata["category"] = None
        metadata["name"] = None
        metadata["department"] = None
        metadata["diary_numbers"] = "[]"
        metadata["pdf"] = False

        if fail:
            return metadata, [], None

        letter = Parser._extract_letter(html_text)
        if not letter:
            return metadata, [], None

        text = Parser._hard_coded_fix(normalized_title)
        words = text.split()

        if len(words) < 4:
            return metadata, [], None

        metadata["type"] = words[0]
        metadata["date"] = Parser._extract_date(letter)
        metadata["year"] = words[1].split("-")[0]
        metadata["category"] = words[2]
        metadata["name"] = " ".join(words[3:])
        metadata["department"] = Parser.extract_department(letter)
        metadata["diary_numbers"] = json.dumps(
            Parser.extract_diary_numbers(letter), ensure_ascii=False
        )
        metadata["pdf"] = "laddaNerPdf" in html_text

        attachments = []
        while "/regleringsbrev/bilaga/" in html_text:
            html_text = html_text[html_text.index("bilaga/") + 7 :]
            attachments.append(
                {
                    "id": int(html_text[: html_text.index('"')]),
                    "rbid": rbid,
                    "name": html_text[
                        html_text.index("\r\n") : html_text.index("</a>")
                    ].strip(),
                }
            )

        return metadata, attachments, letter

    @staticmethod
    def extract_department(letter: str) -> str | None:
        """Read the issuing department from the original letterhead."""
        header = BeautifulSoup(
            letter,
            "html.parser",
            parse_only=SoupStrainer(class_=["avs", "depNamn", "departement"]),
        )
        department = header.find(class_=["avs", "depNamn", "departement"])
        if department is None:
            return None
        return Parser._normalize_whitespace(department.get_text(" ", strip=True)) or None

    @staticmethod
    def extract_diary_numbers(letter: str) -> list[str]:
        """Read diary-number entries from the original letterhead, as printed."""
        tree = LexborHTMLParser(letter)
        diary = tree.css_first("#BrevHuvud #DiarieNr, .universe_tbl .diarie")
        if diary is None:
            header = tree.css_first(".documentHead, .section1")
            right_column = (
                header.css_first('td[style*="width:3.0cm"]') if header else None
            )
            cells = right_column.css("td") if right_column else []
            diary = cells[-1] if cells else None
        if diary is None:
            return []

        markup = re.sub(r"<br\b[^>]*>", "\n", diary.html, flags=re.IGNORECASE)
        text = LexborHTMLParser(markup).text(separator=" ", strip=False)
        lines = []
        for raw_line in text.splitlines():
            line = Parser._normalize_whitespace(raw_line)
            if line and lines and lines[-1].endswith("/"):
                lines[-1] += line
            elif line:
                lines.append(line)
        numbers = []
        pattern = re.compile(
            r"(?:[A-Za-zÅÄÖåäö]{1,4}\s*/?\s*)?\d{2,4}\s*/\s*\d+"
            r"|\b\d{3}-\d{3,5}-\d{2}/\d{2}\b"
        )
        for line in lines:
            if re.fullmatch(r"\((?:delvis|slutligt|slutlig)\)", line, re.I):
                if numbers:
                    numbers[-1] += f" {line}"
                continue
            if not pattern.search(line):
                continue
            line = re.sub(r"\s*,?\s*m\.?\s*fl\.?\s*$", "", line, flags=re.I)
            numbers.append(line.rstrip(",; "))
        return numbers

    @staticmethod
    def _hard_coded_fix(text):
        text = Parser._normalize_whitespace(text)
        text = text.replace("Avseende anslaget", "Anslag")
        text = text.replace(
            "Ändringsbeslut 2003-09-04 Lunds universitet",
            "Ändringsbeslut 2003-09-04 Myndighet Lunds universitet",
        )
        text = text.replace(
            "2003 Avvecklingsmyndigheten för RRV",
            "2003 Myndighet Avvecklingsmyndigheten för RRV",
        )
        text = text.replace(
            "Ändringsbeslut 2003-11-27 Polisväsendet",
            "Ändringsbeslut 2003-11-27 Myndighet Polisväsendet",
        )
        text = text.replace(
            "Ändringsbeslut 2004-11-30 Regeringskansliet",
            "Ändringsbeslut 2004-11-30 Myndighet Regeringskansliet",
        )
        text = text.replace(
            "Ändringsbeslut 2004-01-29 Ändring avseende A:014 samt B:019 FI",
            "Ändringsbeslut 2004-01-29 Anslag A:014 samt B:019 FI",
        )
        text = text.replace(
            "Ändringsbeslut 2004-01-29 Ändring avseende A:005 M",
            "Ändringsbeslut 2004-01-29 Anslag A:005 M",
        )

        return text

    @staticmethod
    def _extract_date(text: str) -> str | None:
        pattern = r"\b\d{4}-\d{2}-\d{2}\b"
        dates = re.findall(pattern, text)

        if dates:
            return dates[0]

    @staticmethod
    def _extract_title(html_text: str) -> str:
        return html_text[html_text.index("<title>") + 7 : html_text.index("</title>")]

    @staticmethod
    def _extract_letter(html_text: str) -> str | None:
        if "<section" not in html_text or "</section>" not in html_text:
            return None

        return html_text[
            html_text.index("<section") : html_text.index("</section>") + 10
        ]

    @staticmethod
    def _is_missing_letter_page(
        response, html_text: str, normalized_title: str
    ) -> bool:
        lowered_title = normalized_title.lower()

        return (
            response.status_code == 404
            or 'class="pagenotfound"' in html_text
            or "/Specialsidor/404/" in html_text
            or "kunde inte hittas" in lowered_title
            or normalized_title == "Regleringsbrev"
        )

    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()
