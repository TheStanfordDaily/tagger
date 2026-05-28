import os
import sys
from urllib.parse import urlparse, parse_qs

import requests

from html_to_xquark import html_to_xquark

USER_AGENT = {"User-agent": "9Ds8MnNbYcg5t376c8m6"}
API_BASE = "https://stanforddaily.com/wp-json/wp/v2/posts"


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


def convert(wp_url: str) -> str:
    """Fetch a WordPress post by its admin edit URL and return XQuarkXPress-tagged text."""
    post_id = post_id_from_url(wp_url)
    data = fetch_post(post_id)

    title = data["title"]["rendered"]
    authors = data.get("parsely", {}).get("meta", {}).get("creator", [])
    byline = ", ".join(authors) if authors else "AUTHOR"
    body_html = data["content"]["rendered"]

    body = html_to_xquark(body_html)

    result = (
        f"@headline:{title}\n"
        f"@byline:By {byline.upper()}\n"
        "@bysub:"
        f"@normalcopy:\n"
        f"{body}"
    )

    os.makedirs("output", exist_ok=True)
    out_path = os.path.join("output", f"{title}.txt")
    with open(out_path, "w") as f:
        f.write(result)
    print(f"Written to {out_path}")

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python wp_to_xquark.py <wp-admin-edit-url>")
        sys.exit(1)

    convert(sys.argv[1])
