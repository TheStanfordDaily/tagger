import os
import sys
import json
import importlib.util
from urllib.parse import urlparse, parse_qs

import requests

USER_AGENT = {"User-Agent": "StanfordDailyPrintTagger/1.0 (+https://stanforddaily.com)"}
API_BASE = "https://stanforddaily.com/wp-json/wp/v2/posts"

SECTION_TAG_MAP = {
    "news": ("NEWS", "9.21", "@byline", "@bysub"),
    "sports": ("SPORTS", "9.21", "@byline", "@bysub"),
    "opinions": ("OPINIONS", "9.21", "@byline", "@bysub"),
    "arts & life": ("ARTS & LIFE", "9.30", "@A&Lbyline", "@A&Lbysub"),
    "the grind": ("ARTS & LIFE", "9.30", "@A&Lbyline", "@A&Lbysub"),
    "humor": ("ARTS & LIFE", "9.30", "@A&Lbyline", "@A&Lbysub"),
}
DEFAULT_SECTION = SECTION_TAG_MAP["news"]


def _normalcopy_before_first_non_italic_paragraph(body: str) -> str:
    """Place ``@normalcopy:`` after any leading italic editor's note."""
    lines = body.splitlines()
    for index, line in enumerate(lines):
        paragraph = line.strip()
        is_italic = (
            paragraph.startswith(("<@CEIt>", "<@CEBoldital>"))
            and paragraph.endswith("<@$p>")
        )
        if not is_italic:
            lines[index] = f"@normalcopy:{line}"
            return "\n".join(lines)
    # Preserve a valid normal-copy tag even if the source contained only an
    # italic note (or no body) and therefore has no prose paragraph to mark.
    return f"{body}\n@normalcopy:".lstrip("\n")


def _section_template(section: str) -> tuple[str, str, str, str]:
    value = (section or "").lower().strip()
    aliases = {
        "opinion": "opinions",
        "op-ed": "opinions",
        "op-eds": "opinions",
        "arts and life": "arts & life",
        "grind": "the grind",
    }
    value = aliases.get(value, value)
    return SECTION_TAG_MAP.get(value, DEFAULT_SECTION)


def build_xquark(headline: str, section: str, authors: list[tuple[str, str]], body: str) -> str:
    """Build the standard, import-ready template for an article.

    Individual author/byline pairs are deliberate: Quark needs each author in
    its own tagged pair, and empty position fields must not produce ``@bysub``.
    """
    header, version, byline_tag, bysub_tag = _section_template(section)
    if not authors:
        authors = [("AUTHOR", "")]
    bylines = []
    for name, position in authors:
        name = str(name).strip()
        if not name:
            continue
        bylines.append(f"{byline_tag}:By {name.upper()}")
        if position and str(position).strip():
            bylines.append(f"{bysub_tag}:{str(position).strip().title()}")
    if not bylines:
        bylines.append(f"{byline_tag}:By AUTHOR")
    return "\n".join(
        [f"<v{version}><e0>", f"@NewsHeader:{header}", *bylines, _normalcopy_before_first_non_italic_paragraph(body)]
    ).rstrip() + "\n"

def get_sample_json():
    #this is just so we can test using the sample post json
    with open("sample_post_json.txt") as f:
        data = json.load(f)
    return data

def print_notion_view_json():
    """Call the Notion query helper and print its JSON output."""
    api_query_path = os.path.join("notion-experiment", "api-query.py")
    spec = importlib.util.spec_from_file_location("api_query", api_query_path)
    api_query = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api_query)

    rows = api_query.get_notion_view_json()
    print(json.dumps(rows, indent=2))

def post_id_from_url(url: str) -> str:
    """Extract post ID from a WP admin edit URL or a ?p= permalink."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    if "post" in params:
        return params["post"][0]
    if "p" in params:
        return params["p"][0]
    raise ValueError(f"Could not find post ID in URL: {url}")


def fetch_post(post_id: str) -> dict:
    """Fetch a public WordPress post; inaccessible posts require manual work."""
    url = f"{API_BASE}/{post_id}"
    try:
        response = requests.get(url, headers=USER_AGENT, timeout=30)
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not fetch public WordPress post {post_id}: {exc}. Add it manually.") from exc
    if response.status_code != 200:
        raise RuntimeError(
            f"Public WordPress post {post_id} is unavailable (HTTP {response.status_code}). Add it manually."
        )
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(f"Public WordPress post {post_id} returned invalid JSON. Add it manually.") from exc


def convert(
    wp_url: str,
    authors: list[tuple[str, str]] | None = None,
    section: str = "",
    filename_stem: str | None = None,
) -> str:
    """Fetch a WordPress post and return XQuarkXPress-tagged text.

    authors: list of (name, position) pairs from Notion; falls back to WP
             parsely data if not provided.
    section: section name used to select byline/bysub tag style.
    filename_stem: output filename without extension; defaults to post title.
    """
    from html_to_xquark import html_to_xquark

    data = fetch_post(post_id_from_url(wp_url))
    title = data["title"]["rendered"]
    body = html_to_xquark(data["content"]["rendered"])

    if not authors:
        wp_creators = data.get("parsely", {}).get("meta", {}).get("creator", [])
        authors = [(name, "") for name in wp_creators]

    result = build_xquark(title, section, authors, body)

    os.makedirs("OUTPUT", exist_ok=True)
    out_path = os.path.join("OUTPUT", f"{filename_stem or title}.txt")
    with open(out_path, "w") as f:
        f.write(result)
    print(f"Written to {out_path}")

    return result


if __name__ == "__main__":
    # Keep this legacy command useful, but route all writes through the
    # manifest/report-aware entry point.
    from main import cli

    raise SystemExit(cli(sys.argv[1:]))
