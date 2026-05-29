"""Notion API helpers for the Stanford Daily XQuark tagging pipeline."""

import os
import importlib.util

PRINT_WEEK_FILTER = "✅ This Week"
PRINT_STATUS_FILTER = "Ready for Copy"
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


def get_filtered_rows() -> list:
    """Return rows for this week's print-ready articles."""
    return [
        r for r in get_all_rows()
        if r.get("Print Week") == PRINT_WEEK_FILTER
        and r.get("Print Status") == PRINT_STATUS_FILTER
        and r.get("Web Status") == WEB_STATUS_FILTER
    ]


def find_row_for_url(wp_url: str) -> dict | None:
    """Return the first Notion row whose 'WP Post' matches wp_url, or None."""
    for row in get_all_rows():
        if row.get("WP Post") == wp_url:
            return row
    return None


def parse_writer_title(value) -> list[tuple[str, str]]:
    """Parse the 'Writer / Title' Notion field into (name, position) pairs.

    Accepts a people-type list or a text field formatted as
    "Name / Position", comma-separated for multiple authors.
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
        else:
            pairs.append((entry, ""))
    return pairs


def section_from_row(row: dict) -> str:
    return row.get("Section") or row.get("Desk") or ""


def filename_stem_from_row(row: dict, fallback: str) -> str:
    slug = row.get("Slug (Print)") or fallback
    return "".join(c for c in str(slug) if c not in r'\/:*?"<>|').strip()
