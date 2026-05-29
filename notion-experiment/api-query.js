const fs = require("node:fs");
const path = require("node:path");

loadEnvFile();

const NOTION_TOKEN = process.env.NOTION_TOKEN;
const VIEW_ID = process.env.NOTION_VIEW_ID;
const NOTION_VERSION = "2026-03-11";
const PAGE_SIZE = 100;
const PAGE_RETRIEVE_CONCURRENCY = 3;

if (!NOTION_TOKEN) {
  throw new Error("Missing NOTION_TOKEN environment variable.");
}

if (!VIEW_ID) {
  throw new Error("Missing NOTION_VIEW_ID environment variable.");
}

function loadEnvFile(filePath = path.join(process.cwd(), ".env")) {
  if (!fs.existsSync(filePath)) {
    return;
  }

  const envFile = fs.readFileSync(filePath, "utf8");

  for (const line of envFile.split(/\r?\n/)) {
    const trimmed = line.trim();

    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }

    const equalsIndex = trimmed.indexOf("=");

    if (equalsIndex === -1) {
      continue;
    }

    const key = trimmed.slice(0, equalsIndex).trim();
    let value = trimmed.slice(equalsIndex + 1).trim();

    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }

    if (!process.env[key]) {
      process.env[key] = value;
    }
  }
}

async function notionFetch(path, options = {}) {
  const response = await fetch(`https://api.notion.com/v1${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${NOTION_TOKEN}`,
      "Content-Type": "application/json",
      "Notion-Version": NOTION_VERSION,
      ...options.headers,
    },
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Notion API error ${response.status}: ${body}`);
  }

  return response.json();
}

async function getAllViewRecords(viewId) {
  const firstPage = await notionFetch(`/views/${viewId}/queries`, {
    method: "POST",
    body: JSON.stringify({ page_size: PAGE_SIZE }),
  });

  const records = [...firstPage.results];
  let cursor = firstPage.next_cursor;

  try {
    while (cursor) {
      const page = await notionFetch(
        `/views/${viewId}/queries/${firstPage.id}?start_cursor=${cursor}&page_size=${PAGE_SIZE}`
      );

      records.push(...page.results);
      cursor = page.next_cursor;
    }
  } finally {
    await notionFetch(`/views/${viewId}/queries/${firstPage.id}`, {
      method: "DELETE",
    });
  }

  return records;
}

async function getPage(pageId) {
  return notionFetch(`/pages/${pageId}`);
}

async function mapWithConcurrency(items, limit, mapper) {
  const results = new Array(items.length);
  let nextIndex = 0;

  async function worker() {
    while (nextIndex < items.length) {
      const currentIndex = nextIndex;
      nextIndex += 1;
      results[currentIndex] = await mapper(items[currentIndex], currentIndex);
    }
  }

  const workers = Array.from(
    { length: Math.min(limit, items.length) },
    () => worker()
  );

  await Promise.all(workers);
  return results;
}

function getPlainText(richText = []) {
  return richText.map((part) => part.plain_text).join("");
}

function simplifyProperty(property) {
  if (!property) {
    return null;
  }

  switch (property.type) {
    case "title":
      return getPlainText(property.title);
    case "rich_text":
      return getPlainText(property.rich_text);
    case "number":
      return property.number;
    case "select":
      return property.select?.name ?? null;
    case "multi_select":
      return property.multi_select.map((option) => option.name);
    case "status":
      return property.status?.name ?? null;
    case "date":
      return property.date;
    case "checkbox":
      return property.checkbox;
    case "url":
      return property.url;
    case "email":
      return property.email;
    case "phone_number":
      return property.phone_number;
    case "people":
      return property.people.map((person) => person.name ?? person.id);
    case "files":
      return property.files.map((file) => ({
        name: file.name,
        url: file.type === "external" ? file.external.url : file.file.url,
      }));
    case "relation":
      return property.relation.map((page) => page.id);
    case "rollup":
      return simplifyRollup(property.rollup);
    case "formula":
      return simplifyFormula(property.formula);
    case "created_time":
      return property.created_time;
    case "created_by":
      return property.created_by?.name ?? property.created_by?.id ?? null;
    case "last_edited_time":
      return property.last_edited_time;
    case "last_edited_by":
      return property.last_edited_by?.name ?? property.last_edited_by?.id ?? null;
    case "unique_id":
      return property.unique_id
        ? `${property.unique_id.prefix ?? ""}${property.unique_id.number}`
        : null;
    default:
      return property[property.type] ?? null;
  }
}

function simplifyFormula(formula) {
  if (!formula) {
    return null;
  }

  switch (formula.type) {
    case "string":
      return formula.string;
    case "number":
      return formula.number;
    case "boolean":
      return formula.boolean;
    case "date":
      return formula.date;
    default:
      return formula[formula.type] ?? null;
  }
}

function simplifyRollup(rollup) {
  if (!rollup) {
    return null;
  }

  switch (rollup.type) {
    case "number":
      return rollup.number;
    case "date":
      return rollup.date;
    case "array":
      return rollup.array.map(simplifyProperty);
    case "unsupported":
      return null;
    default:
      return rollup[rollup.type] ?? null;
  }
}

function simplifyRecord(record) {
  const row = {
    id: record.id,
    url: record.url,
  };

  for (const [columnName, property] of Object.entries(record.properties ?? {})) {
    row[columnName] = simplifyProperty(property);
  }

  return row;
}

async function main() {
  const viewRecords = await getAllViewRecords(VIEW_ID);
  const fullPages = await mapWithConcurrency(
    viewRecords,
    PAGE_RETRIEVE_CONCURRENCY,
    (record) => getPage(record.id)
  );
  const rows = fullPages.map(simplifyRecord);

  console.log(`Fetched ${rows.length} records from view ${VIEW_ID}.`);
  console.log(JSON.stringify(rows, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
