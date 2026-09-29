"""Notion API helpers for the Stanford Daily XQuark tagging pipeline."""

import os
import importlib.util
import re
from datetime import datetime
from urllib.parse import parse_qs, urlparse

PRINT_WEEK_FILTER = "✅ This Week"
PRINT_STATUS_FILTER = "To Print"
WEB_STATUS_FILTER = "Finaled & published"

PRINT_SECTION_TAGS = {
    "news": "NEW",
    "sports": "SPO",
    "opinions": "OPS",
    "opinion": "OPS",
    "arts & life": "A&L",
    "arts and life": "A&L",
    "the grind": "GRI",
    "grind": "GRI",
    "humor": "HUM",
}


def _load_notion_module():
    path = os.path.join("notion-experiment", "api-query.py")
    spec = importlib.util.spec_from_file_location("api_query", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def get_all_rows() -> list:
    """Return all rows from the configured Notion view."""
    return _load_notion_module().get_notion_view_json()


def _is_community_submission(row: dict) -> bool:
    writer = row.get("Writer / Title") or ""
    if isinstance(writer, list):
        return any("from the community" in str(item).lower() for item in writer)
    return "from the community" in str(writer).lower()


def get_batch_rows() -> tuple[list[dict], list[dict]]:
    """Return exportable rows and Community rows deliberately left unbatched.

    It applies the active weekly status filters, then keeps Community stories
    out of the batch while recording them for the review report.
    """
    selected_rows = [
        row for row in get_all_rows()
        if row.get("Print Week") == PRINT_WEEK_FILTER
        and row.get("Print Status") == PRINT_STATUS_FILTER
        and row.get("Web Status") == WEB_STATUS_FILTER
    ]
    community = [row for row in selected_rows if _is_community_submission(row)]
    return [row for row in selected_rows if not _is_community_submission(row)], community


def get_filtered_rows() -> list:
    """Return exportable rows (compatibility wrapper for older callers)."""
    return get_batch_rows()[0]


def find_row_for_url(wp_url: str) -> dict | None:
    """Return the matching Notion row, accepting equivalent WordPress URLs."""
    def post_id(value: str | None) -> str | None:
        params = parse_qs(urlparse(value or "").query)
        return (params.get("post") or params.get("p") or [None])[0]

    requested_id = post_id(wp_url)
    for row in get_all_rows():
        if row.get("WP Post") == wp_url:
            return row
        if requested_id and post_id(row.get("WP Post")) == requested_id:
            return row
    return None


def parse_writer_title(value) -> list[tuple[str, str]]:
    """Parse the 'Writer / Title' Notion field into (name, position) pairs.

    Accepts a people-type list or a text field formatted as
    "Name / Position", comma-separated for multiple authors. A compact
    ``Name/Story title`` value is also used by some run sheets; the story-title
    part is metadata, not a bysub, so it is intentionally omitted.
    """
    if not value:
        return []
    if isinstance(value, list):
        return [(str(n), "") for n in value if n]
    pairs = []
    for entry in str(value).split(","):
        entry = entry.strip()
        if not entry:
            continue
        if " / " in entry:
            name, _, pos = entry.partition(" / ")
            pairs.append((name.strip(), pos.strip()))
        elif "/" in entry:
            name, _, _title = entry.partition("/")
            if name.strip():
                pairs.append((name.strip(), ""))
        else:
            pairs.append((entry, ""))
    return pairs


def writer_title_error(value) -> str | None:
    """Return a reviewable error for ambiguous ``Writer / Title`` text.

    Valid text entries are ``Name / Role`` pairs separated with commas. A bare
    name is also valid when the article has no bysub. People-type lists are
    already structured by Notion and need no delimiter validation.
    """
    if not value or isinstance(value, list):
        return None
    for entry in str(value).split(","):
        entry = entry.strip()
        if not entry:
            return "contains an empty author entry"
        if "/" in entry and " / " not in entry:
            return "use spaces around each slash: Name / Role"
        # This catches e.g. "Writer / Title and Writer / Title" without
        # rejecting role names such as "Arts and Culture Editor".
        if re.search(r"\band\s+[^/]+\s/\s", entry, re.I):
            return "separate multiple Name / Role pairs with commas, not 'and'"
        if entry.count(" / ") > 1:
            return "contains more than one Name / Role pair; separate authors with commas"
        if " / " in entry:
            name, _, role = entry.partition(" / ")
            if not name.strip() or not role.strip():
                return "each Name / Role pair needs both a name and a role"
    return None


def section_from_row(row: dict) -> str:
    return row.get("Section") or row.get("Desk") or ""


def paper_date_digits(value: str) -> str:
    """Validate a supplied paper date and return its YYYYMMDD representation."""
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) != 8:
        raise ValueError("paper date must be YYYYMMDD")
    try:
        datetime.strptime(digits, "%Y%m%d")
    except ValueError as error:
        raise ValueError("paper date must be a valid YYYYMMDD date") from error
    return digits


def filename_stem_from_row(row: dict, paper_date: str, fallback: str = "") -> str:
    """Build ``<section tag><lowercase slug><YYYYMMDD>`` for print output."""
    section = (section_from_row(row) or "").strip().lower()
    section_tag = PRINT_SECTION_TAGS.get(section)
    if not section_tag:
        raise ValueError(f"missing or unsupported print section: {section_from_row(row)!r}")

    slug = row.get("Slug (Print)") or fallback
    slug = "".join(c for c in str(slug) if c not in r'\/:*?"<>|').strip().lower()
    if not slug:
        raise ValueError("missing Slug (Print)")

    return f"{section_tag}{slug}{paper_date_digits(paper_date)}"
