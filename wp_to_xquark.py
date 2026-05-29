import os
import sys
import json
import importlib.util
from urllib.parse import urlparse, parse_qs

import requests

USER_AGENT = {"User-agent": "9Ds8MnNbYcg5t376c8m6"}
API_BASE = "https://stanforddaily.com/wp-json/wp/v2/posts"

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
    return json.dumps(rows, indent=2)

def retrieve_notion_data(json):
    #given a json for a single article, returns important variables
    url = json["url"]
    writer_title = json["Writer / Title"]
    writer,title = parse_writer_title(writer_title)
    print_slug = json["Slug (Print)"]
    desk = json["desk"]
    section = json["section"]
    web_status = json["Web Status"]
    print_week = json["Print Week"]
    return url,writer,title,print_slug,desk,section,web_status,print_week

def parse_writer_title(writer_title):
    #for a string in the format "writer / title" it returns both as tuple
    writer, title = writer_title.split("/", 1)
    return writer.strip(), title.strip()

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
    from html_to_xquark import html_to_xquark

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

    print_notion_view_json()

    convert(sys.argv[1])
