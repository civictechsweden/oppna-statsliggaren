import html
import re


class Parser(object):
    @staticmethod
    def parse_latest_remote_rbid(response) -> int:
        html_text = html.unescape(response.text)

        return int(sorted(html_text.split("rbid=")[1:], reverse=True)[0].split("&")[0])

    @staticmethod
    def parse_metadata(response):
        html_text = html.unescape(response.text)

        text = html_text[html_text.index("<title>") + 7 : html_text.index("</title>")]

        fail = text == "Regleringsbrev - Statskontoret"

        letter = (
            None
            if fail or "<section" not in html_text
            else html_text[
                html_text.index("<section") : html_text.index("</section>") + 10
            ]
        )

        text = Parser._hard_coded_fix(text)
        words = text.split()

        metadata = {"rbid": response.id}
        metadata["type"] = None if fail else words[0]
        metadata["date"] = None if fail or not letter else Parser._extract_date(letter)
        metadata["year"] = None if fail else words[1].split("-")[0]
        metadata["category"] = None if fail else words[2]
        metadata["name"] = None if fail else " ".join(words[3:-2])
        metadata["pdf"] = "laddaNerPdf" in html_text

        attachments = []
        if not fail:
            while "/regleringsbrev/bilaga/" in html_text:
                html_text = html_text[html_text.index("bilaga/") + 7 :]
                attachments.append(
                    {
                        "id": int(html_text[: html_text.index('"')]),
                        "rbid": response.id,
                        "name": html_text[
                            html_text.index("\r\n") : html_text.index("</a>")
                        ].strip(),
                    }
                )

        return metadata, attachments, letter

    @staticmethod
    def parse_metadatas(futures):
        items = []
        all_attachments = []
        letters = {}

        for future in futures:
            metadata, attachments, letter = Parser.parse_metadata(future)
            if metadata["name"]:
                items.append(metadata)
                letters[future.id] = letter
            all_attachments.extend(attachments)

        return items, all_attachments, letters

    @staticmethod
    def _hard_coded_fix(text):
        text = text.replace("Avseende anslaget", "Anslag")
        text = text.replace(
            "Ändringsbeslut  2003-09-04 Lunds universitet",
            "Ändringsbeslut 2003-09-04 Myndighet Lunds universitet",
        )
        text = text.replace(
            "Ändringsbeslut  2003-11-27 Polisväsendet",
            "Ändringsbeslut 2003-11-27 Myndighet Polisväsendet",
        )
        text = text.replace(
            "Ändringsbeslut 2004-11-30 Regeringskansliet",
            "Ändringsbeslut 2004-11-30 Myndighet Regeringskansliet",
        )
        text = text.replace(
            "Ändringsbeslut  2004-01-29 Ändring avseende A:014 samt B:019 FI",
            "Ändringsbeslut 2004-01-29 Anslag A:014 samt B:019 FI",
        )
        text = text.replace(
            "Ändringsbeslut  2004-01-29 Ändring avseende A:005 M",
            "Ändringsbeslut 2004-01-29 Anslag A:005 M",
        )

        return text

    @staticmethod
    def _extract_date(text: str) -> str | None:
        pattern = r"\b\d{4}-\d{2}-\d{2}\b"
        dates = re.findall(pattern, text)

        if dates:
            return dates[0]
