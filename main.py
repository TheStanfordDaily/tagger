"""Entry point for the Stanford Daily XQuark tagging pipeline.

Usage:
  python main.py                # batch: all this-week articles from Notion
  python main.py <wp-edit-url>  # single article (Notion metadata looked up by URL)
"""

import os
import sys

from html_to_xquark import html_to_xquark
from wp_to_xquark import post_id_from_url, fetch_post, build_xquark
from notion_api import (
    get_filtered_rows,
    find_row_for_url,
    parse_writer_title,
    section_from_row,
    filename_stem_from_row,
)

# Section name (lowercase) → (byline_tag, bysub_tag)
SECTION_TAG_MAP = {
    "news": ("@byline", "@bysub"),
    "sports": ("@byline", "@bysub"),
    "opinions": ("@byline", "@bysub"),
    "arts & life": ("@A&Lbyline", "@A&Lbysub"),
    "the grind": ("@A&Lbyline", "@A&Lbysub"),
    "humor": ("@A&Lbyline", "@A&Lbysub"),
}
DEFAULT_TAGS = ("@byline", "@bysub")

def _byline_str(authors: list[tuple[str, str]]) -> str:
    names = [n.upper() for n, _ in authors if n]
    if not names:
        return "AUTHOR"
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " AND " + names[-1]


def build_xquark(headline: str, section: str, authors: list[tuple[str, str]], body: str) -> str:
    byline_tag, bysub_tag = SECTION_TAG_MAP.get((section or "").lower().strip(), DEFAULT_TAGS)
    positions = [pos for _, pos in authors if pos]

    return (
        f"@headline:{headline}\n"
        f"{byline_tag}:By {_byline_str(authors)}\n"
        f"{bysub_tag}:{', '.join(positions)}\n"
        f"@normalcopy:\n"
        f"{body}"
    )


def _resolve_authors(row: dict, wp_data: dict) -> list[tuple[str, str]]:
    authors = parse_writer_title(row.get("Writer / Title"))
    if authors:
        print(f"    Authors (Notion): {authors}")
    else:
        wp_creators = wp_data.get("parsely", {}).get("meta", {}).get("creator", [])
        authors = [(name, "") for name in wp_creators]
        print(f"    Authors (WP fallback): {authors}")
    return authors


def _write_output(stem: str, text: str) -> str:
    os.makedirs("output", exist_ok=True)
    out_path = os.path.join("output", f"{stem}.txt")
    with open(out_path, "w") as f:
        f.write(text)
    return out_path


def convert_row(row: dict) -> tuple[str, str]:
    """Convert a single Notion row to (filename_stem, xquark_text)."""
    wp_url = row.get("WP Post")
    if not wp_url:
        raise ValueError(f"Row {row.get('id')} has no WP Post URL")

    print(f"  Fetching WP post: {wp_url}")
    data = fetch_post(post_id_from_url(wp_url))
    headline = data["title"]["rendered"]
    print(f"  Headline: {headline}")

    section = section_from_row(row)
    print(f"  Section: {section!r}")

    authors = _resolve_authors(row, data)

    print(f"  Converting HTML body...")
    body = html_to_xquark(data["content"]["rendered"])

    text = build_xquark(headline, section, authors, body)
    stem = filename_stem_from_row(row, headline)
    print(f"  Filename stem: {stem!r}")
    return stem, text


def batch():
    """Process all this-week Notion articles and write output files."""
    print("Fetching Notion rows...")
    rows = get_filtered_rows()
    print(f"Found {len(rows)} article(s) matching filters.\n")

    ok = fail = 0
    for i, row in enumerate(rows, 1):
        slug = row.get("Slug (Print)") or row.get("id")
        print(f"[{i}/{len(rows)}] {slug}")
        try:
            stem, text = convert_row(row)
            out_path = _write_output(stem, text)
            print(f"  Written: {out_path}\n")
            ok += 1
        except Exception as exc:
            print(f"  ERROR: {exc}\n", file=sys.stderr)
            fail += 1

    print(f"Done: {ok} written, {fail} failed.")


def single(wp_url: str) -> str:
    """Convert one article by WP URL, using Notion metadata if a row is found."""
    print(f"Looking up Notion row for: {wp_url}")
    row = find_row_for_url(wp_url)
    if row:
        print(f"  Notion row found: {row.get('Slug (Print)') or row.get('id')}")
    else:
        print("  No Notion row found — falling back to WP metadata only.")

    print(f"Fetching WP post...")
    data = fetch_post(post_id_from_url(wp_url))
    headline = data["title"]["rendered"]
    print(f"  Headline: {headline}")

    if row:
        section = section_from_row(row)
        authors = _resolve_authors(row, data)
        stem = filename_stem_from_row(row, headline)
    else:
        section = ""
        wp_creators = data.get("parsely", {}).get("meta", {}).get("creator", [])
        authors = [(name, "") for name in wp_creators]
        stem = headline

    print(f"  Section: {section!r}")
    print(f"  Converting HTML body...")
    body = html_to_xquark(data["content"]["rendered"])

    text = build_xquark(headline, section, authors, body)
    out_path = _write_output(stem, text)
    print(f"Written to {out_path}")
    return text


if __name__ == "__main__":
    if len(sys.argv) == 1:
        batch()
    elif len(sys.argv) == 2:
        single(sys.argv[1])
    else:
        print("Usage:")
        print("  python main.py                # batch: all this-week articles from Notion")
        print("  python main.py <wp-edit-url>  # single article")
        sys.exit(1)
