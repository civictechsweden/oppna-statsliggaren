import re

from bs4 import BeautifulSoup


class Cleaner(object):
    @staticmethod
    def clean_letter_html(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")

        Cleaner._normalize_sup_references(soup)
        Cleaner._merge_split_headings(soup)
        Cleaner._merge_numbered_paragraph_continuations(soup)
        Cleaner._normalize_finansiering_headings(soup)
        Cleaner._normalize_generic_heading_hierarchy(soup)
        Cleaner._normalize_anslag_tables(soup)
        Cleaner._normalize_bemyndigande_tables(soup)
        Cleaner._normalize_distribution_lists(soup)
        Cleaner._group_fotnot_blocks(soup)

        return str(soup)

    @staticmethod
    def clean_markdown(markdown: str) -> str:
        markdown = markdown.replace("\r\n", "\n")
        lines = [line if line.strip() else "" for line in markdown.split("\n")]

        cleaned_lines = []
        blank_run = 0
        for line in lines:
            if line == "":
                blank_run += 1
                if blank_run > 1:
                    continue
            else:
                blank_run = 0
            cleaned_lines.append(line.rstrip())

        return "\n".join(cleaned_lines).strip() + "\n"

    @staticmethod
    def _merge_split_headings(soup: BeautifulSoup) -> None:
        for header_div in soup.select("div.header-div"):
            headings = header_div.select("h1, h2, h3, h4, h5, h6")
            if not headings:
                continue

            text = " ".join(
                heading.get_text(" ", strip=True) for heading in headings if heading
            ).strip()
            if not text:
                continue

            merged_heading = soup.new_tag(headings[0].name)
            merged_heading.string = text
            header_div.replace_with(merged_heading)

    @staticmethod
    def _normalize_finansiering_headings(soup: BeautifulSoup) -> None:
        in_finansiering = False

        for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            text = heading.get_text(" ", strip=True)

            if text == "FINANSIERING":
                in_finansiering = True
                continue

            if not in_finansiering:
                continue

            if heading.name == "h1":
                in_finansiering = False
                continue

            if text.startswith("Utgiftsområde "):
                heading.name = "h4"
            elif re.match(r"^\d+:\d+\s", text):
                heading.name = "h5"
            elif text.startswith("Villkor för anslag "):
                Cleaner._replace_with_strong_paragraph(heading, soup)
            elif re.match(r"^ap\.\d+\s", text, flags=re.IGNORECASE):
                heading.name = "h6"

    @staticmethod
    def _normalize_generic_heading_hierarchy(soup: BeautifulSoup) -> None:
        current_numbered_level = None
        villkor_level = None

        for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            text = heading.get_text(" ", strip=True)
            numeric_match = re.match(r"^(\d+(?:\.\d+)*)\s", text)

            if numeric_match:
                current_numbered_level = numeric_match.group(1).count(".") + 2
                villkor_level = None
                continue

            if text == "Villkor" and current_numbered_level is not None:
                villkor_level = min(6, current_numbered_level + 1)
                heading.name = f"h{villkor_level}"
                continue

            if villkor_level is not None:
                current_level = int(heading.name[1])
                target_level = min(6, villkor_level + 1)
                if current_level <= villkor_level:
                    heading.name = f"h{target_level}"

    @staticmethod
    def _normalize_anslag_tables(soup: BeautifulSoup) -> None:
        for summary_table in soup.select("table.table-anslagtilldelade-myndighet"):
            anchor = Cleaner._wrapped_table_anchor(summary_table)
            anslagspost_tables = Cleaner._collect_following_tables(
                anchor, "table-anslagtilldelade-anslagspost-ap"
            )

            normalized_table = Cleaner._build_anslag_table(
                soup, summary_table, anslagspost_tables
            )
            if normalized_table is None:
                continue

            anchor.replace_with(normalized_table)
            for table in anslagspost_tables:
                table.decompose()

    @staticmethod
    def _normalize_bemyndigande_tables(soup: BeautifulSoup) -> None:
        for table in soup.select("table.table-bemyndigandentabell"):
            sections = Cleaner._build_bemyndigande_sections(soup, table)
            if not sections:
                continue

            wrapper = soup.new_tag("div")
            for section in sections:
                wrapper.append(section)

            table.replace_with(wrapper)

    @staticmethod
    def _normalize_distribution_lists(soup: BeautifulSoup) -> None:
        for container in soup.select("#BrevFot_KopiaTill"):
            items = []
            for child in container.find_all("div", recursive=False):
                text = child.get_text(" ", strip=True)
                if text:
                    items.append(text)

            if not items:
                continue

            list_tag = soup.new_tag("ul")
            for item in items:
                li = soup.new_tag("li")
                li.string = item
                list_tag.append(li)

            container.replace_with(list_tag)

    @staticmethod
    def _group_fotnot_blocks(soup: BeautifulSoup) -> None:
        visited = set()

        for fotnot in soup.select("div.fotnot"):
            if id(fotnot) in visited:
                continue

            group = [fotnot]
            visited.add(id(fotnot))

            sibling = fotnot.find_next_sibling()
            while sibling and sibling.name == "div" and "fotnot" in sibling.get("class", []):
                group.append(sibling)
                visited.add(id(sibling))
                sibling = sibling.find_next_sibling()

            paragraph = soup.new_tag("p")
            emphasis = soup.new_tag("em")

            for i, item in enumerate(group):
                if i > 0:
                    emphasis.append(soup.new_tag("br"))
                emphasis.append(Cleaner._fotnot_text(item))

            paragraph.append(emphasis)
            group[0].replace_with(paragraph)

            for item in group[1:]:
                item.decompose()

    @staticmethod
    def _fotnot_text(item) -> str:
        sup = item.find("sup", recursive=False)
        if not sup:
            return item.get_text(" ", strip=True)

        marker = sup.get_text(" ", strip=True)
        text = item.get_text(" ", strip=True)
        remainder = text[len(marker) :].strip() if text.startswith(marker) else text
        return f"[{marker}] {remainder}".strip()

    @staticmethod
    def _wrapped_table_anchor(table):
        parent = table.parent
        if parent and parent.name == "div" and parent.find_all(recursive=False) == [table]:
            return parent

        return table

    @staticmethod
    def _normalize_sup_references(soup: BeautifulSoup) -> None:
        for sup in soup.find_all("sup"):
            text = sup.get_text(" ", strip=True)
            if re.fullmatch(r"\d+", text):
                sup.replace_with(f"[{text}]")

    @staticmethod
    def _merge_numbered_paragraph_continuations(soup: BeautifulSoup) -> None:
        for container in soup.find_all(["div", "section", "article"]):
            paragraphs = container.find_all("p", recursive=False)
            if len(paragraphs) < 2:
                continue

            i = 1
            while i < len(paragraphs):
                current = paragraphs[i]
                previous = paragraphs[i - 1]
                current_text = current.get_text(" ", strip=True)
                previous_text = previous.get_text(" ", strip=True)

                if (
                    previous_text
                    and current_text
                    and re.match(r"^\d+\.\s", previous_text)
                    and not re.match(r"^\d+\.\s", current_text)
                ):
                    previous.append(" ")
                    for child in list(current.contents):
                        previous.append(child.extract())
                    current.decompose()
                    paragraphs.pop(i)
                    continue

                i += 1

    @staticmethod
    def _collect_following_tables(anchor, class_name: str) -> list:
        tables = []
        sibling = anchor.find_next_sibling()

        while sibling and sibling.name == "table":
            if class_name not in sibling.get("class", []):
                break
            tables.append(sibling)
            sibling = sibling.find_next_sibling()

        return tables

    @staticmethod
    def _build_anslag_table(
        soup: BeautifulSoup, summary_table, anslagspost_tables: list
    ):
        summary_cells = summary_table.select("tr th, tr td")
        if len(summary_cells) < 2:
            return None

        table = soup.new_tag("table")
        tbody = soup.new_tag("tbody")
        table.append(tbody)

        tbody.append(
            Cleaner._build_row(
                soup,
                [
                    ("th", ""),
                    ("th", summary_cells[0].get_text(" ", strip=True)),
                    ("th", summary_cells[1].get_text(" ", strip=True)),
                ],
            )
        )

        for anslagspost_table in anslagspost_tables:
            for row in anslagspost_table.select("tr"):
                if "invisible-header" in row.get("class", []):
                    continue

                cells = row.find_all(["th", "td"])
                if not cells:
                    continue

                tbody.append(
                    Cleaner._build_row(
                        soup,
                        [
                            (cell.name, cell.get_text(" ", strip=True))
                            for cell in cells
                        ],
                    )
                )

        return table

    @staticmethod
    def _build_bemyndigande_header_cells(thead):
        if not thead:
            return None

        rows = thead.find_all("tr", recursive=False)
        if len(rows) < 2:
            return None

        top_cells = rows[0].find_all("th", recursive=False)
        bottom_cells = rows[1].find_all("th", recursive=False)
        if len(top_cells) < 3 or len(bottom_cells) < 5:
            return None

        first_label = top_cells[0].get_text(" ", strip=True)
        bemyndigande_label = top_cells[1].get_text(" ", strip=True)
        utgifter_label = top_cells[2].get_text(" ", strip=True)
        year_labels = [cell.get_text(" ", strip=True) for cell in bottom_cells]

        return [
            ("th", first_label),
            ("th", f"{bemyndigande_label} {year_labels[0]}"),
            ("th", f"{utgifter_label} {year_labels[1]}"),
            ("th", f"{utgifter_label} {year_labels[2]}"),
            ("th", f"{utgifter_label} {year_labels[3]}"),
            ("th", f"{utgifter_label} {year_labels[4]}"),
        ]

    @staticmethod
    def _build_bemyndigande_sections(soup: BeautifulSoup, table) -> list:
        header_cells = Cleaner._build_bemyndigande_header_cells(table.find("thead"))
        tbody = table.find("tbody")
        if not header_cells or not tbody:
            return []

        sections = []
        current_label = None
        current_rows = []

        for row in tbody.find_all("tr", recursive=False):
            cells = row.find_all(["th", "td"], recursive=False)
            if not cells:
                continue

            if len(cells) == 1 and cells[0].get("colspan"):
                if current_label and current_rows:
                    sections.append(
                        Cleaner._build_bemyndigande_section(
                            soup, current_label, header_cells, current_rows
                        )
                    )
                current_label = cells[0].get_text(" ", strip=True)
                current_rows = []
                continue

            current_rows.append(
                [(cell.name, cell.get_text(" ", strip=True)) for cell in cells]
            )

        if current_label and current_rows:
            sections.append(
                Cleaner._build_bemyndigande_section(
                    soup, current_label, header_cells, current_rows
                )
            )

        return sections

    @staticmethod
    def _build_bemyndigande_section(
        soup: BeautifulSoup, label: str, header_cells: list, rows: list
    ):
        container = soup.new_tag("div")

        label_paragraph = soup.new_tag("p")
        strong = soup.new_tag("strong")
        strong.string = label
        label_paragraph.append(strong)
        container.append(label_paragraph)

        table = soup.new_tag("table")
        tbody = soup.new_tag("tbody")
        table.append(tbody)
        tbody.append(Cleaner._build_row(soup, header_cells))

        for row in rows:
            tbody.append(Cleaner._build_row(soup, row))

        container.append(table)
        return container

    @staticmethod
    def _build_row(soup: BeautifulSoup, cells: list[tuple[str, str]]):
        row = soup.new_tag("tr")
        for tag_name, text in cells:
            cell = soup.new_tag(tag_name)
            cell.string = text
            row.append(cell)
        return row

    @staticmethod
    def _replace_with_strong_paragraph(heading, soup: BeautifulSoup) -> None:
        paragraph = soup.new_tag("p")
        strong = soup.new_tag("strong")
        strong.string = heading.get_text(" ", strip=True)
        paragraph.append(strong)
        heading.replace_with(paragraph)
