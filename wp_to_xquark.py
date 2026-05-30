import os
import sys
import json
import importlib.util
from urllib.parse import urlparse, parse_qs

import requests

USER_AGENT = {"User-agent": "9Ds8MnNbYcg5t376c8m6"}
API_BASE = "https://stanforddaily.com/wp-json/wp/v2/posts"

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



def build_xquark(headline: str, section: str, authors: list[tuple[str, str]], body: str) -> str:
    byline_tag, bysub_tag = SECTION_TAG_MAP.get((section or "").lower().strip(), DEFAULT_TAGS)

    if not authors:
        authors = [("AUTHOR", "")]

    bylines = "".join(
        f"{byline_tag}:By {name.upper()}\n{bysub_tag}:{pos}\n"
        for name, pos in authors
    )

    return f"@headline:{headline}\n{bylines}@normalcopy:\n{body}"


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
    url = f"{API_BASE}/{post_id}"
    response = requests.get(url, headers=USER_AGENT)
    response.raise_for_status()
    return response.json()


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

    os.makedirs("output", exist_ok=True)
    out_path = os.path.join("output", f"{filename_stem or title}.txt")
    with open(out_path, "w") as f:
        f.write(result)
    print(f"Written to {out_path}")

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python wp_to_xquark.py <wp-admin-edit-url>")
        sys.exit(1)

    print_notion_view_json()

    convert(sys.argv[1])
