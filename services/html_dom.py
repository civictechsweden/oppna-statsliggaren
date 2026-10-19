"""Small DOM operations used by the letter normalizers, backed by Lexbor."""

from selectolax.lexbor import LexborHTMLParser, LexborNode


def parse_html(html: str) -> LexborNode:
    return LexborHTMLParser(html).root.parent


def parse_fragment(html: str) -> LexborNode:
    # A stable container also retains every top-level sibling in the fragment.
    parser = LexborHTMLParser(f'<div id="letter-fragment">{html}</div>')
    return parser.css_first("#letter-fragment")


def children(node: LexborNode) -> list[LexborNode]:
    result = []
    child = node.child
    while child is not None:
        result.append(child)
        child = child.next
    return result


def descendants(node: LexborNode):
    for child in children(node):
        yield child
        yield from descendants(child)


def is_tag(node) -> bool:
    return isinstance(node, LexborNode) and node.is_element_node


def is_text(node) -> bool:
    return isinstance(node, str) or (isinstance(node, LexborNode) and node.is_text_node)


def markup(value) -> str:
    if isinstance(value, LexborNode):
        return value.text() if value.is_text_node else value.html
    return str(value)


def strings(node: LexborNode) -> list[str]:
    return [
        child.text().strip()
        for child in descendants(node)
        if child.is_text_node and child.text().strip()
    ]


def text(node: LexborNode, separator: str = "", strip: bool = False) -> str:
    values = [child.text() for child in descendants(node) if child.is_text_node]
    if node.is_text_node:
        values = [node.text()]
    if strip:
        values = [value.strip() for value in values if value.strip()]
    return separator.join(values)


def select(node: LexborNode, selector: str) -> list[LexborNode]:
    return [match for match in node.css(selector) if match != node]


def select_one(node: LexborNode, selector: str) -> LexborNode | None:
    return next(iter(select(node, selector)), None)


def find_all(node: LexborNode, name=None, recursive: bool = True, string=None):
    candidates = descendants(node) if recursive else children(node)
    matches = []
    for child in candidates:
        if not child.is_element_node:
            continue
        if isinstance(name, str) and child.tag != name:
            continue
        if isinstance(name, (list, tuple, set)) and child.tag not in name:
            continue
        if hasattr(name, "search") and not name.search(child.tag):
            continue
        if string is not None:
            value = single_string(child)
            if callable(string):
                if not string(value):
                    continue
            elif value != string:
                continue
        matches.append(child)
    return matches


def find(node: LexborNode, name=None, recursive: bool = True, string=None):
    return next(iter(find_all(node, name, recursive, string)), None)


def single_string(node: LexborNode) -> str | None:
    content = children(node)
    if len(content) != 1:
        return None
    child = content[0]
    if child.is_text_node:
        return child.text()
    return single_string(child) if child.is_element_node else None


def get_attr(node: LexborNode, name: str, default=None):
    value = node.attributes.get(name, default)
    if name == "class" and isinstance(value, str):
        return value.split()
    return value


def set_attr(node: LexborNode, name: str, value) -> None:
    node.attrs[name] = " ".join(value) if isinstance(value, list) else str(value)


def set_attrs(node: LexborNode, attrs: dict) -> None:
    for name in list(node.attributes):
        del node.attrs[name]
    for name, value in attrs.items():
        set_attr(node, name, value)


def clear(node: LexborNode) -> None:
    for child in children(node):
        child.decompose()


def set_text(node: LexborNode, value: str) -> None:
    clear(node)
    node.insert_child(value)


def rename(node: LexborNode, name: str) -> LexborNode:
    replacement = node.parser.create_node(name)
    set_attrs(replacement, node.attributes)
    for child in children(node):
        replacement.insert_child(child)
    node.replace_with(replacement)
    return replacement


def detach(node: LexborNode) -> LexborNode:
    # Decompose removes a subtree; cloning first keeps the extracted content alive.
    detached = node.clone()
    node.decompose()
    return detached


def next_sibling(node: LexborNode) -> LexborNode | None:
    sibling = node.next
    while sibling is not None and not sibling.is_element_node:
        sibling = sibling.next
    return sibling


def comments(node: LexborNode):
    return [child for child in descendants(node) if child.is_comment_node]
