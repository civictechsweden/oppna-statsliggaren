import html


class Parser(object):
    @staticmethod
    def parse_metadata(future):
        response = future.result()
        response = html.unescape(response.text)
        text = response[response.index("<title>") + 7 : response.index("</title>")]

        if text == "Ekonomistyrningsverket":
            return

        return {"text": text}

    @staticmethod
    def parse_metadatas(futures):
        items = []
        for future in futures:
            items.append(Parser.parse_page(future))

        return items
