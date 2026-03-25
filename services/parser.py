import html
import re


class Parser(object):
    @staticmethod
    def parse_latest_remote_rbid(response) -> int:
        html_text = html.unescape(response.text)

        return int(sorted(html_text.split("rbid=")[1:], reverse=True)[0].split("&")[0])

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
