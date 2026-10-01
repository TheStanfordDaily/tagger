"""DOM-aware HTML to XQuark tagged-text conversion."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, NavigableString, Tag
from unidecode import unidecode


MEDIA_TAGS = {"img", "figure", "figcaption", "video", "audio", "iframe", "embed", "object", "svg", "picture", "source"}
NON_CONTENT_TAGS = {"script", "style", "noscript"}
UNSUPPORTED_TAGS = {"u", "s", "strike", "table", "thead", "tbody", "tfoot", "tr", "td", "th", "pre", "code", "sup", "sub"}
BLOCK_TAGS = {"p", "div", "section", "article", "header", "footer", "aside", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"}
CONTACT_RE = re.compile(r"^contact\s+.+?\s+at\s+[^\s@]+@[^\s@]+\.[^\s.]+\.?$", re.I)
CONTACT_LIKE_RE = re.compile(r"\bcontact\b|@stanford\.edu\b", re.I)
WHOLE_ITALIC_RE = re.compile(r"^<@CE(?:It|Boldital)>.*<@\$p>$", re.S)
ITALIC_OPEN_RE = re.compile(r"^(<@CE(?:It|Boldital)>)(.*)$", re.S)
OPENING_QUOTES = {'"', '\u201c', '\u2018'}


@dataclass
class ConversionNotes:
    """Details for the review report. Pass this to ``html_to_xquark``."""

    removed: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)
    contact_warnings: list[str] = field(default_factory=list)

    def add_once(self, bucket: str, message: str) -> None:
        values = getattr(self, bucket)
        if message not in values:
            values.append(message)


def _plain(tag: Tag) -> str:
    return " ".join(tag.get_text(" ", strip=True).split())


def _normalise_text(value: str) -> str:
    """Apply legacy substitutions without using regexes on HTML itself."""
    value = value.replace("\xa0", " ")
    try:
        value.encode("mac_roman")
    except UnicodeEncodeError:
        value = unidecode(value)
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    value = re.sub(r"(?<!\w)[\u2018\u2019'](\d{2})(?!\d)", r"<\\#213>\1", value)
    value = re.sub(r"\s*(?:\u2014|--)\s*", r"<\\p><\\_><\\p>", value)
    value = re.sub(r"(?:\u2026|\.\.\.)", r"<\\p>...<\\p>", value)
    return value


def _style_tag(style: frozenset[str]) -> str:
    if style == frozenset({"bold", "italic"}):
        return "<@CEBoldital>"
    if "bold" in style:
        return "<@CEBold>"
    if "italic" in style:
        return "<@CEIt>"
    return ""


def _inline(node: Tag | NavigableString, style: frozenset[str] = frozenset()) -> list[tuple[str, frozenset[str]]]:
    if isinstance(node, NavigableString):
        return [(_normalise_text(str(node)), style)]
    if not isinstance(node, Tag):
        return []
    name = node.name.lower()
    if name == "br":
        return [("\n", style)]
    if name in {"strong", "b"}:
        style = style | {"bold"}
    elif name in {"em", "i"}:
        style = style | {"italic"}
    values: list[tuple[str, frozenset[str]]] = []
    for child in node.children:
        values.extend(_inline(child, style))
    return values


def _render_pieces(pieces: list[tuple[str, frozenset[str]]]) -> str:
    result: list[str] = []
    current = frozenset()
    for value, style in pieces:
        if not value:
            continue
        if style != current:
            if current:
                result.append("<@$p>")
            if style:
                result.append(_style_tag(style))
            current = style
        result.append(value)
    if current:
        result.append("<@$p>")
    return "".join(result).strip()


def _render_inline(tag: Tag) -> str:
    return _render_pieces(_inline(tag))


def _remove_unsupported(soup: BeautifulSoup, notes: ConversionNotes) -> None:
    # A figure is removed as one unit so the image and caption are not reported
    # twice.  This makes the report concise and actionable.
    for tag in list(soup.find_all(MEDIA_TAGS)):
        if tag.parent is None:
            continue
        detail = _plain(tag)
        notes.add_once("removed", f"removed {tag.name}" + (f": {detail[:100]}" if detail else ""))
        tag.decompose()
    for tag in list(soup.find_all(NON_CONTENT_TAGS)):
        notes.add_once("removed", f"removed {tag.name}")
        tag.decompose()
    for tag in soup.find_all(UNSUPPORTED_TAGS):
        notes.add_once("unsupported", f"{tag.name} formatting exported as plain text")
    for tag in soup.find_all("blockquote"):
        notes.add_once("unsupported", "blockquote exported as plain text")


def _is_correction(tag: Tag) -> bool:
    return bool(re.match(r"^(?:update|correction)\s*:", _plain(tag), re.I))


def _render_list(list_tag: Tag, notes: ConversionNotes) -> list[str]:
    ordered = list_tag.name.lower() == "ol"
    lines: list[str] = []
    index = 1
    for li in list_tag.find_all("li", recursive=False):
        pieces: list[tuple[str, frozenset[str]]] = []
        for child in li.contents:
            if isinstance(child, Tag) and child.name.lower() in {"ul", "ol"}:
                continue
            pieces.extend(_inline(child))
        text = _render_pieces(pieces)
        if ordered:
            lines.append(f"@DigitIndent:{index}. <\\i><@normalcopy>{text}")
            index += 1
        else:
            lines.append(f"@Bullet indent:<@Bullet>l<@\\$p><\\i> {text}")
        for child in li.find_all(["ul", "ol"], recursive=False):
            notes.add_once("unsupported", "nested list exported with a fresh indentation level")
            lines.extend(_render_list(child, notes))
    return lines


def _first_visible_character(line: str, start: int = 0) -> int | None:
    """Find visible text without mistaking an XQuark tag for story text."""
    index = start
    while index < len(line):
        if line[index] == "<":
            end = line.find(">", index + 1)
            if end != -1:
                index = end + 1
                continue
        if not line[index].isspace():
            return index
        index += 1
    return None


def _apply_dropcap(body: str, dropcap_tag: str) -> str:
    """Apply the legacy opening dropcap and following ``<*d(0)>`` reset."""
    paragraphs = body.split("\n\t")
    target = None
    for index, paragraph in enumerate(paragraphs):
        stripped = paragraph.strip()
        if not stripped:
            continue
        if WHOLE_ITALIC_RE.fullmatch(stripped):
            # An A&L editor's note leads with its italic tag, followed by the
            # tab/space indent expected by the print template.
            match = ITALIC_OPEN_RE.fullmatch(stripped)
            if match:
                paragraphs[index] = f"{match.group(1)}\t {match.group(2)}"
            continue
        # Lists and contact lines are not prose paragraphs and cannot take a
        # dropcap.
        if stripped.startswith("@"):
            continue
        target = index
        break
    if target is None:
        return body

    # Dropcap paragraphs are the exception to the regular initial-tab rule:
    # the dropcap tag itself begins the line.
    paragraph = paragraphs[target].lstrip()
    first = _first_visible_character(paragraph)
    if first is None:
        return body
    width = 1
    end = first + 1
    # The legacy tagger widens the box when a quoted sentence opens the story.
    if paragraph[first] in OPENING_QUOTES:
        letter = _first_visible_character(paragraph, first + 1)
        if letter is not None and paragraph[letter].isalpha():
            width = 2
            end = letter + 1
    elif not paragraph[first].isalpha():
        letter = _first_visible_character(paragraph, first + 1)
        if letter is None or not paragraph[letter].isalpha():
            return body
        first = letter
        end = letter + 1
    marker = f"<{dropcap_tag}><*bn(7.2,1,0)*d({width},6)>"
    paragraphs[target] = paragraph[:first] + marker + paragraph[first:end] + "<@$p>" + paragraph[end:]

    # The original tagger inserts this marker after the first dropcap
    # paragraph; it restores normal settings for the following prose copy.
    for index in range(target + 1, len(paragraphs)):
        if paragraphs[index].strip() and not paragraphs[index].lstrip().startswith("@"):
            paragraphs[index] = "<*d(0)> " + paragraphs[index]
            break
    rendered = "\n\t".join(paragraphs)
    # If an italic note precedes the story, the separator normally contributes
    # a tab before the dropcap tag. The dropcap tag must begin its own line.
    return rendered.replace(f"\n\t<{dropcap_tag}>", f"\n<{dropcap_tag}>", 1)


def html_to_xquark(
    html: str,
    notes: ConversionNotes | None = None,
    dropcap_tag: str | None = None,
) -> str:
    """Convert a WordPress HTML fragment to XQuark text.

    ``notes`` is optional for backward compatibility; passing it captures
    removals and review warnings without printing during conversion.
    """
    notes = notes or ConversionNotes()
    soup = BeautifulSoup(html or "", "html.parser")
    _remove_unsupported(soup, notes)
    lines: list[str] = []

    def visit(node: Tag | NavigableString) -> None:
        if isinstance(node, NavigableString):
            text = _normalise_text(str(node)).strip()
            if text:
                lines.append(text)
            return
        if not isinstance(node, Tag):
            return
        name = node.name.lower()
        if name in {"ul", "ol"}:
            lines.extend(_render_list(node, notes))
            return
        if name in BLOCK_TAGS:
            # Gutenberg occasionally wraps normal paragraphs in section/div
            # containers. Preserve the paragraph boundaries instead of
            # flattening those wrappers into one long line.
            has_block_children = any(
                isinstance(child, Tag)
                and child.name.lower() in BLOCK_TAGS | {"ul", "ol"}
                for child in node.children
            )
            if has_block_children:
                for child in node.children:
                    visit(child)
                return
            if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                # Print templates treat web headings as standalone bold
                # paragraphs; discard any nested web styling for consistency.
                text = _normalise_text(_plain(node)).strip()
                if text:
                    lines.append(f"<@CEBold>{text}<@$p>")
                return
            if _is_correction(node):
                notes.add_once("removed", f"removed correction/update: {_plain(node)[:120]}")
                return
            text = _render_inline(node)
            if text:
                lines.extend(part.strip() for part in text.split("\n") if part.strip())
            return
        for child in node.children:
            visit(child)

    for child in soup.contents:
        visit(child)

    output: list[str] = []
    for line in lines:
        plain = re.sub(r"<[^>]+>", "", line).strip()
        if CONTACT_RE.match(plain):
            output.append(f"@@line:{line}")
        else:
            if CONTACT_LIKE_RE.search(plain):
                notes.add_once("contact_warnings", f"unrecognized contact line: {plain[:140]}")
            output.append(line)
    # A tab marks each prose paragraph in the print template. Prefix the first
    # item as well: joining with ``\n\t`` alone only tabbed later paragraphs.
    body = ("\t" + "\n\t".join(output)).rstrip() if output else ""
    return _apply_dropcap(body, dropcap_tag) if dropcap_tag else body
