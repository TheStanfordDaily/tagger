# Print tagger

This tool exports print-ready, XQuark-tagged MacRoman `.txt` files directly
from the Notion print run sheet and their WordPress posts. It replaces the old
copy/paste RTF workflow. Complete the [one-time setup](#one-time-setup) before
running the weekly print workflow.

## Weekly print workflow

1. In Notion, set every story for this print batch to **This Week**, **To
   Print**, and **Finaled & published**. “From the Community” stories are not
   batch-exported; the report lists them under **Do manually**.

2. Before starting a new batch, move any approved old exports into the layout
   folder or archive them elsewhere. Then delete the `OUTPUT` folder in Finder.
   This permanently removes the prior generated `.txt` files, review report,
   and `manifest.json`; do not delete it until those files are no longer needed.

3. Run the batch with the paper's publication day in `D` or `DD` format:

   ```bash
   python3 main.py --publication-date 29
   ```

4. Read `OUTPUT/review-report.txt`. Resolve everything in **Do manually** and
   inspect any formatting/removal warnings. Verify each file’s section header,
   headline/byline, lists, and removed correction or media content.

5. Copy approved files into the layout folder. Files are named
   `<SECTION><lowercase slug><D-or-DD>.txt`, for example
   `NEWcampusvote29.txt`. The supplied day is used for every filename
   in that batch; it does not come from Notion.
   Keep `manifest.json` while working on this batch and never hand-edit it.

6. To re-export one story during the same batch, provide the same
   `--publication-date` value and its WordPress admin edit URL (or a permalink
   containing `?p=ID`):

   ```bash
   python3 main.py --publication-date 29 'https://stanforddaily.com/wp-admin/post.php?post=123&action=edit'
   ```

## When something goes wrong

- **No eligible rows:** check all three Notion statuses, then rerun.
- **Bad/missing WordPress URL:** use the WordPress edit URL with `post=ID` or a URL with
  `?p=ID`, fix it in Notion, and rerun.
- **Missing author, title, or print slug:** fill in Notion's `Writer / Title`
  and `Slug (Print)` (WordPress authors are used only as a fallback), then
  rerun.
- **Malformed `Writer / Title`:** use `Name / Role` for one author and
  separate multiple authors with commas: `Name / Role, Name / Role`. Do not
  use `Name/Role` or join author pairs with “and”; those stories appear under
  **Do manually**.
- **Slug collision / existing output from another story:** give the stories
  distinct print slugs. During an active batch, do not delete or edit individual
  manifest entries to force an overwrite.
- **Notion, WordPress, or network failure:** check connectivity and rerun. A
  WordPress 401, 403, or 404 means the post is not public yet. Confirm the article
  has been published before re-running the script.
- **Unsupported formatting or special Opinion layout:** Finish that layout manually.

In every case, correct the source data and rerun the batch or the one-URL
command. The review report is regenerated on each run.

## One-time setup

1. Use Python 3.10 or newer, then install the dependencies:

   ```bash
   python3 -m pip install requests beautifulsoup4 Unidecode certifi
   ```

2. Create a local `.env` file in this folder (it is ignored by Git):

   ```text
   NOTION_TOKEN=secret_...
   ```

   The Notion integration must have access to the configured view. Never
   commit or share the token. The non-secret view ID is committed in
   `notion-experiment/notion-view.json`; update that file if the team changes
   Notion views. WordPress posts must be publicly readable; inaccessible posts
   are listed under **Do manually**.
