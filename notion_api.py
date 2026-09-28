"""Notion API helpers for the Stanford Daily XQuark tagging pipeline."""

import os
import importlib.util
from urllib.parse import parse_qs, urlparse

PRINT_WEEK_FILTER = "✅ This Week"
PRINT_STATUS_FILTER = "To Print"
WEB_STATUS_FILTER = "Finaled & published"


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


def section_from_row(row: dict) -> str:
    return row.get("Section") or row.get("Desk") or ""


def filename_stem_from_row(row: dict, fallback: str) -> str:
    slug = row.get("Slug (Print)") or fallback
    return "".join(c for c in str(slug) if c not in r'\/:*?"<>|').strip()
