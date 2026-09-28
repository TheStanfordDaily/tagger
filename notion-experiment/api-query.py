import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import ssl
import certifi

ctx = ssl.create_default_context(cafile=certifi.where())
#Kayla's Pycharm has certification problems so this makes it use certify's trusted CA bundle

NOTION_VERSION = "2026-03-11"
PAGE_SIZE = 100
PAGE_RETRIEVE_CONCURRENCY = 3
DEFAULT_ENV_FILES = (
    Path.cwd() / ".env",
    Path(__file__).resolve().parent / ".env",
)
VIEW_CONFIG_FILE = Path(__file__).resolve().parent / "notion-view.json"


def load_env_file(file_path):
    path = Path(file_path)

    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        trimmed = line.strip()

        if not trimmed or trimmed.startswith("#"):
            continue

        key, separator, value = trimmed.partition("=")

        if not separator:
            continue

        key = key.strip()
        value = value.strip()

        if (
            (value.startswith('"') and value.endswith('"'))
            or (value.startswith("'") and value.endswith("'"))
        ):
            value = value[1:-1]

        os.environ.setdefault(key, value)


def load_env_files(env_file=None):
    if env_file:
        load_env_file(env_file)
        return

    for file_path in DEFAULT_ENV_FILES:
        load_env_file(file_path)


def load_view_id() -> str | None:
    """Read the non-secret committed Notion view configuration."""
    if not VIEW_CONFIG_FILE.exists():
        return None
    try:
        value = json.loads(VIEW_CONFIG_FILE.read_text(encoding="utf-8")).get("notion_view_id")
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Invalid Notion view configuration: {error}") from error
    return str(value).strip() if value else None


def notion_fetch(path, notion_token, method="GET", body=None, headers=None):
    request_headers = {
        "Authorization": f"Bearer {notion_token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
        **(headers or {}),
    }

    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")

    request = Request(
        f"https://api.notion.com/v1{path}",
        data=data,
        headers=request_headers,
        method=method,
    )

    try:
        with urlopen(request, context=ctx) as response:
            response_body = response.read().decode("utf-8")
    except HTTPError as error:
        error_body = error.read().decode("utf-8")
        raise RuntimeError(f"Notion API error {error.code}: {error_body}") from error

    if not response_body:
        return None

    return json.loads(response_body)


def get_all_view_records(view_id, notion_token):
    first_page = notion_fetch(
        f"/views/{view_id}/queries",
        notion_token,
        method="POST",
        body={"page_size": PAGE_SIZE},
    )

    records = list(first_page["results"])
    cursor = first_page.get("next_cursor")

    try:
        while cursor:
            query = urlencode({"start_cursor": cursor, "page_size": PAGE_SIZE})
            page = notion_fetch(
                f"/views/{view_id}/queries/{first_page['id']}?{query}",
                notion_token,
            )

            records.extend(page["results"])
            cursor = page.get("next_cursor")
    finally:
        notion_fetch(
            f"/views/{view_id}/queries/{first_page['id']}",
            notion_token,
            method="DELETE",
        )

    return records


def get_page(page_id, notion_token):
    return notion_fetch(f"/pages/{page_id}", notion_token)


def get_plain_text(rich_text=None):
    return "".join(part.get("plain_text", "") for part in rich_text or [])


def simplify_property(property_value):
    if not property_value:
        return None

    property_type = property_value.get("type")

    if property_type == "title":
        return get_plain_text(property_value.get("title"))
    if property_type == "rich_text":
        return get_plain_text(property_value.get("rich_text"))
    if property_type == "number":
        return property_value.get("number")
    if property_type == "select":
        select = property_value.get("select")
        return select.get("name") if select else None
    if property_type == "multi_select":
        return [option.get("name") for option in property_value.get("multi_select", [])]
    if property_type == "status":
        status = property_value.get("status")
        return status.get("name") if status else None
    if property_type == "date":
        return property_value.get("date")
    if property_type == "checkbox":
        return property_value.get("checkbox")
    if property_type == "url":
        return property_value.get("url")
    if property_type == "email":
        return property_value.get("email")
    if property_type == "phone_number":
        return property_value.get("phone_number")
    if property_type == "people":
        return [
            person.get("name") or person.get("id")
            for person in property_value.get("people", [])
        ]
    if property_type == "files":
        return [
            {
                "name": file.get("name"),
                "url": file.get("external", {}).get("url")
                if file.get("type") == "external"
                else file.get("file", {}).get("url"),
            }
            for file in property_value.get("files", [])
        ]
    if property_type == "relation":
        return [page.get("id") for page in property_value.get("relation", [])]
    if property_type == "rollup":
        return simplify_rollup(property_value.get("rollup"))
    if property_type == "formula":
        return simplify_formula(property_value.get("formula"))
    if property_type == "created_time":
        return property_value.get("created_time")
    if property_type == "created_by":
        created_by = property_value.get("created_by")
        return (created_by.get("name") or created_by.get("id")) if created_by else None
    if property_type == "last_edited_time":
        return property_value.get("last_edited_time")
    if property_type == "last_edited_by":
        last_edited_by = property_value.get("last_edited_by")
        return (
            last_edited_by.get("name") or last_edited_by.get("id")
            if last_edited_by
            else None
        )
    if property_type == "unique_id":
        unique_id = property_value.get("unique_id")
        if not unique_id:
            return None
        return f"{unique_id.get('prefix') or ''}{unique_id.get('number')}"

    return property_value.get(property_type)


def simplify_formula(formula):
    if not formula:
        return None

    formula_type = formula.get("type")

    if formula_type == "string":
        return formula.get("string")
    if formula_type == "number":
        return formula.get("number")
    if formula_type == "boolean":
        return formula.get("boolean")
    if formula_type == "date":
        return formula.get("date")

    return formula.get(formula_type)


def simplify_rollup(rollup):
    if not rollup:
        return None

    rollup_type = rollup.get("type")

    if rollup_type == "number":
        return rollup.get("number")
    if rollup_type == "date":
        return rollup.get("date")
    if rollup_type == "array":
        return [simplify_property(item) for item in rollup.get("array", [])]
    if rollup_type == "unsupported":
        return None

    return rollup.get(rollup_type)


def simplify_record(record):
    row = {
        "id": record.get("id"),
        "url": record.get("url"),
    }

    for column_name, property_value in record.get("properties", {}).items():
        row[column_name] = simplify_property(property_value)

    return row


def get_notion_view_json(view_id=None, notion_token=None, env_file=None):
    """Return the simplified Notion view rows as a JSON-serializable list."""
    load_env_files(env_file)

    notion_token = notion_token or os.environ.get("NOTION_TOKEN")
    view_id = view_id or load_view_id() or os.environ.get("NOTION_VIEW_ID")

    if not notion_token:
        raise RuntimeError("Missing NOTION_TOKEN environment variable.")

    if not view_id:
        raise RuntimeError("Missing NOTION_VIEW_ID environment variable.")

    view_records = get_all_view_records(view_id, notion_token)

    with ThreadPoolExecutor(max_workers=PAGE_RETRIEVE_CONCURRENCY) as executor:
        full_pages = list(
            executor.map(lambda record: get_page(record["id"], notion_token), view_records)
        )

    return [simplify_record(page) for page in full_pages]


def main():
    rows = get_notion_view_json()
    view_id = os.environ.get("NOTION_VIEW_ID")

    print(f"Fetched {len(rows)} records from view {view_id}.")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(error, file=sys.stderr)
        sys.exit(1)
