import html
import re


class Parser(object):
    @staticmethod
    def parse_metadata(future):
        response = future.result()
        response = html.unescape(response.text)

        text = response[response.index("<title>") + 7 : response.index("</title>")]

        fail = text == "Ekonomistyrningsverket"

        letter = (
            None
            if fail or "<section" not in response
            else response[
                response.index("<section") : response.index("</section>") + 10
            ]
        )

        text = Parser._hard_coded_fix(text)
        words = text.split()

        metadata = {"rbid": future.id}
        metadata["text"] = None if fail else text
        metadata["type"] = None if fail else words[0]
        metadata["date"] = None if fail or not letter else Parser._extract_date(letter)
        metadata["year"] = None if fail else words[1].split("-")[0]
        metadata["category"] = None if fail else words[2]
        metadata["name"] = None if fail else " ".join(words[3:])
        metadata["pdf"] = "laddaNerPdf" in response

        attachments = []

        if not fail:
            while "/Regleringsbrev/Bilaga?BilageID=" in response:
                response = response[response.index("BilageID=") + 9 :]
                attachments.append(
                    {
                        "id": int(response[: response.index('"')]),
                        "rbid": future.id,
                        "name": response[
                            response.index("\r\n") : response.index("</a>")
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
            if metadata["text"]:
                items.append(metadata)
                letters[future.id] = letter
            all_attachments.extend(attachments)

        return items, all_attachments, letters

    @staticmethod
    def _hard_coded_fix(text):
        text = text.replace("Avseende anslaget", "Anslag")
        text = text.replace(
            "Avvecklingsmyndigheten", "Myndighet Avvecklingsmyndigheten"
        )
        text = text.replace(
            "Ändringsbeslut 2003-09-04 Lunds universitet",
            "Ändringsbeslut 2003-09-04 Myndighet Lunds universitet",
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
    def _extract_date(text):
        pattern = r"\b\d{4}-\d{2}-\d{2}\b"
        dates = re.findall(pattern, text)

        if dates:
            return dates[0]
