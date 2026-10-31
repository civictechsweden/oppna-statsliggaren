import re

from selectolax.lexbor import LexborNode

from services import html_dom as dom


class Cleaner(object):
    @staticmethod
    def clean_letter_html(html: str) -> str:
        soup = dom.parse_html(html)

        Cleaner._normalize_sup_references(soup)
        Cleaner._merge_split_headings(soup)
        Cleaner._merge_numbered_paragraph_continuations(soup)
        Cleaner._normalize_finansiering_headings(soup)
        Cleaner._normalize_generic_heading_hierarchy(soup)
        Cleaner._normalize_anslag_tables(soup)
        Cleaner._normalize_bemyndigande_tables(soup)
        Cleaner._normalize_distribution_lists(soup)
        Cleaner._group_fotnot_blocks(soup)

        return dom.markup(soup)

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
    def _merge_split_headings(soup: LexborNode) -> None:
        for header_div in dom.select(soup, "div.header-div"):
            headings = dom.select(header_div, "h1, h2, h3, h4, h5, h6")
            if not headings:
                continue

            text = " ".join(
                dom.text(heading, " ", strip=True) for heading in headings if heading
            ).strip()
            if not text:
                continue

            merged_heading = soup.parser.create_node(headings[0].tag)
            dom.set_text(merged_heading, text)
            header_div.replace_with(merged_heading)

    @staticmethod
    def _normalize_finansiering_headings(soup: LexborNode) -> None:
        in_finansiering = False

        for heading in dom.find_all(soup, ["h1", "h2", "h3", "h4", "h5", "h6"]):
            text = dom.text(heading, " ", strip=True)

            if text == "FINANSIERING":
                in_finansiering = True
                continue

            if not in_finansiering:
                continue

            if heading.tag == "h1":
                in_finansiering = False
                continue

            if text.startswith("Utgiftsområde "):
                heading = dom.rename(heading, "h4")
            elif re.match(r"^\d+:\d+\s", text):
                heading = dom.rename(heading, "h5")
            elif text.startswith("Villkor för anslag "):
                Cleaner._replace_with_strong_paragraph(heading, soup)
            elif re.match(r"^ap\.\d+\s", text, flags=re.IGNORECASE):
                heading = dom.rename(heading, "h6")

    @staticmethod
    def _normalize_generic_heading_hierarchy(soup: LexborNode) -> None:
        current_numbered_level = None
        villkor_level = None

        for heading in dom.find_all(soup, ["h1", "h2", "h3", "h4", "h5", "h6"]):
            text = dom.text(heading, " ", strip=True)
            numeric_match = re.match(r"^(\d+(?:\.\d+)*)\s", text)

            if numeric_match:
                current_numbered_level = numeric_match.group(1).count(".") + 2
                villkor_level = None
                continue

            if text == "Villkor" and current_numbered_level is not None:
                villkor_level = min(6, current_numbered_level + 1)
                heading = dom.rename(heading, f"h{villkor_level}")
                continue

            if villkor_level is not None:
                current_level = int(heading.tag[1])
                target_level = min(6, villkor_level + 1)
                if current_level <= villkor_level:
                    heading = dom.rename(heading, f"h{target_level}")

    @staticmethod
    def _normalize_anslag_tables(soup: LexborNode) -> None:
        for summary_table in dom.select(soup, "table.table-anslagtilldelade-myndighet"):
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
    def _normalize_bemyndigande_tables(soup: LexborNode) -> None:
        for table in dom.select(soup, "table.table-bemyndigandentabell"):
            sections = Cleaner._build_bemyndigande_sections(soup, table)
            if not sections:
                continue

            wrapper = soup.parser.create_node("div")
            for section in sections:
                wrapper.insert_child(section)

            table.replace_with(wrapper)

    @staticmethod
    def _normalize_distribution_lists(soup: LexborNode) -> None:
        for container in dom.select(soup, "#BrevFot_KopiaTill"):
            items = []
            for child in dom.find_all(container, "div", recursive=False):
                text = dom.text(child, " ", strip=True)
                if text:
                    items.append(text)

            if not items:
                continue

            list_tag = soup.parser.create_node("ul")
            for item in items:
                li = soup.parser.create_node("li")
                dom.set_text(li, item)
                list_tag.insert_child(li)

            container.replace_with(list_tag)

    @staticmethod
    def _group_fotnot_blocks(soup: LexborNode) -> None:
        visited = set()

        for fotnot in dom.select(soup, "div.fotnot"):
            if fotnot.mem_id in visited:
                continue

            group = [fotnot]
            visited.add(fotnot.mem_id)

            sibling = dom.next_sibling(fotnot)
            while (
                sibling
                and sibling.tag == "div"
                and "fotnot" in dom.get_attr(sibling, "class", [])
            ):
                group.append(sibling)
                visited.add(sibling.mem_id)
                sibling = dom.next_sibling(sibling)

            paragraph = soup.parser.create_node("p")
            emphasis = soup.parser.create_node("em")

            for i, item in enumerate(group):
                if i > 0:
                    emphasis.insert_child(soup.parser.create_node("br"))
                emphasis.insert_child(Cleaner._fotnot_text(item))

            paragraph.insert_child(emphasis)
            group[0].replace_with(paragraph)

            for item in group[1:]:
                item.decompose()

    @staticmethod
    def _fotnot_text(item) -> str:
        sup = dom.find(item, "sup", recursive=False)
        if not sup:
            return dom.text(item, " ", strip=True)

        marker = dom.text(sup, " ", strip=True)
        text = dom.text(item, " ", strip=True)
        remainder = text[len(marker) :].strip() if text.startswith(marker) else text
        return f"[{marker}] {remainder}".strip()

    @staticmethod
    def _wrapped_table_anchor(table):
        parent = table.parent
        if (
            parent
            and parent.tag == "div"
            and dom.find_all(parent, recursive=False) == [table]
        ):
            return parent

        return table

    @staticmethod
    def _normalize_sup_references(soup: LexborNode) -> None:
        for sup in dom.find_all(soup, "sup"):
            text = dom.text(sup, " ", strip=True)
            if re.fullmatch(r"\d+", text):
                sup.replace_with(f"[{text}]")

    @staticmethod
    def _merge_numbered_paragraph_continuations(soup: LexborNode) -> None:
        for container in dom.find_all(soup, ["div", "section", "article"]):
            paragraphs = dom.find_all(container, "p", recursive=False)
            if len(paragraphs) < 2:
                continue

            i = 1
            while i < len(paragraphs):
                current = paragraphs[i]
                previous = paragraphs[i - 1]
                current_text = dom.text(current, " ", strip=True)
                previous_text = dom.text(previous, " ", strip=True)

                if (
                    previous_text
                    and current_text
                    and re.match(r"^\d+\.\s", previous_text)
                    and not re.match(r"^\d+\.\s", current_text)
                ):
                    previous.insert_child(" ")
                    for child in list(dom.children(current)):
                        previous.insert_child(dom.detach(child))
                    current.decompose()
                    paragraphs.pop(i)
                    continue

                i += 1

    @staticmethod
    def _collect_following_tables(anchor, class_name: str) -> list:
        tables = []
        sibling = dom.next_sibling(anchor)

        while sibling and sibling.tag == "table":
            if class_name not in dom.get_attr(sibling, "class", []):
                break
            tables.append(sibling)
            sibling = dom.next_sibling(sibling)

        return tables

    @staticmethod
    def _build_anslag_table(soup: LexborNode, summary_table, anslagspost_tables: list):
        summary_cells = dom.select(summary_table, "tr th, tr td")
        if len(summary_cells) < 2:
            return None

        table = soup.parser.create_node("table")
        tbody = soup.parser.create_node("tbody")
        tbody = dom.append(table, tbody)

        tbody.insert_child(
            Cleaner._build_row(
                soup,
                [
                    ("th", ""),
                    ("th", dom.text(summary_cells[0], " ", strip=True)),
                    ("th", dom.text(summary_cells[1], " ", strip=True)),
                ],
            )
        )

        for anslagspost_table in anslagspost_tables:
            for row in dom.select(anslagspost_table, "tr"):
                if "invisible-header" in dom.get_attr(row, "class", []):
                    continue

                cells = dom.find_all(row, ["th", "td"])
                if not cells:
                    continue

                tbody.insert_child(
                    Cleaner._build_row(
                        soup,
                        [(cell.tag, dom.text(cell, " ", strip=True)) for cell in cells],
                    )
                )

        return table

    @staticmethod
    def _build_bemyndigande_header_cells(thead):
        if not thead:
            return None

        rows = dom.find_all(thead, "tr", recursive=False)
        if len(rows) < 2:
            return None

        top_cells = dom.find_all(rows[0], "th", recursive=False)
        bottom_cells = dom.find_all(rows[1], "th", recursive=False)
        if len(top_cells) < 3 or len(bottom_cells) < 5:
            return None

        first_label = dom.text(top_cells[0], " ", strip=True)
        bemyndigande_label = dom.text(top_cells[1], " ", strip=True)
        utgifter_label = dom.text(top_cells[2], " ", strip=True)
        year_labels = [dom.text(cell, " ", strip=True) for cell in bottom_cells]

        return [
            ("th", first_label),
            ("th", f"{bemyndigande_label} {year_labels[0]}"),
            ("th", f"{utgifter_label} {year_labels[1]}"),
            ("th", f"{utgifter_label} {year_labels[2]}"),
            ("th", f"{utgifter_label} {year_labels[3]}"),
            ("th", f"{utgifter_label} {year_labels[4]}"),
        ]

    @staticmethod
    def _build_bemyndigande_sections(soup: LexborNode, table) -> list:
        header_cells = Cleaner._build_bemyndigande_header_cells(
            dom.find(table, "thead")
        )
        tbody = dom.find(table, "tbody")
        if not header_cells or not tbody:
            return []

        sections = []
        current_label = None
        current_rows = []

        for row in dom.find_all(tbody, "tr", recursive=False):
            cells = dom.find_all(row, ["th", "td"], recursive=False)
            if not cells:
                continue

            if len(cells) == 1 and dom.get_attr(cells[0], "colspan"):
                if current_label and current_rows:
                    sections.append(
                        Cleaner._build_bemyndigande_section(
                            soup, current_label, header_cells, current_rows
                        )
                    )
                current_label = dom.text(cells[0], " ", strip=True)
                current_rows = []
                continue

            current_rows.append(
                [(cell.tag, dom.text(cell, " ", strip=True)) for cell in cells]
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
        soup: LexborNode, label: str, header_cells: list, rows: list
    ):
        container = soup.parser.create_node("div")

        label_paragraph = soup.parser.create_node("p")
        strong = soup.parser.create_node("strong")
        dom.set_text(strong, label)
        label_paragraph.insert_child(strong)
        container.insert_child(label_paragraph)

        table = soup.parser.create_node("table")
        tbody = soup.parser.create_node("tbody")
        tbody = dom.append(table, tbody)
        tbody.insert_child(Cleaner._build_row(soup, header_cells))

        for row in rows:
            tbody.insert_child(Cleaner._build_row(soup, row))

        container.insert_child(table)
        return container

    @staticmethod
    def _build_row(soup: LexborNode, cells: list[tuple[str, str]]):
        row = soup.parser.create_node("tr")
        for tag_name, text in cells:
            cell = soup.parser.create_node(tag_name)
            dom.set_text(cell, text)
            row.insert_child(cell)
        return row

    @staticmethod
    def _replace_with_strong_paragraph(heading, soup: LexborNode) -> None:
        paragraph = soup.parser.create_node("p")
        strong = soup.parser.create_node("strong")
        dom.set_text(strong, dom.text(heading, " ", strip=True))
        paragraph.insert_child(strong)
        heading.replace_with(paragraph)
