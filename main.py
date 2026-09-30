"""Notion → WordPress → MacRoman XQuark print export.

Usage:
  python main.py                # eligible Notion rows
  python main.py <wp-edit-url>  # one article re-export
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup

from html_to_xquark import ConversionNotes, html_to_xquark
from notion_api import (
    filename_stem_from_row,
    find_row_for_url,
    get_batch_rows,
    parse_writer_title,
    section_from_row,
    writer_title_error,
)
from wp_to_xquark import build_xquark, fetch_post, post_id_from_url


OUTPUT_DIR = Path("OUTPUT")
MANIFEST_PATH = OUTPUT_DIR / "manifest.json"
REPORT_PATH = OUTPUT_DIR / "review-report.txt"


def _macroman_safe(value: str) -> str:
    """Keep output importable by old Quark installations without data errors."""
    result = []
    for char in value:
        try:
            char.encode("mac_roman")
            result.append(char)
        except UnicodeEncodeError:
            # Transliteration is more useful in a print file than a write error.
            from unidecode import unidecode
            result.append(unidecode(char) or "?")
    return "".join(result)


def _clean_headline(value: str) -> str:
    return _macroman_safe(BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True))


@dataclass
class ReviewReport:
    written: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    malformed: list[str] = field(default_factory=list)
    collisions: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    contacts: list[str] = field(default_factory=list)
    failed: int = 0

    def issue(self, kind: str, message: str, failed: bool = False) -> None:
        getattr(self, kind).append(message)
        if failed:
            self.failed += 1

    def include_notes(self, label: str, notes: ConversionNotes) -> None:
        self.unsupported.extend(f"{label}: {item}" for item in notes.unsupported)
        self.removed.extend(f"{label}: {item}" for item in notes.removed)
        self.contacts.extend(f"{label}: {item}" for item in notes.contact_warnings)

    def render(self) -> str:
        do_manually = [*self.skipped, *self.malformed, *self.collisions]
        groups = (
            ("Do manually", do_manually),
            ("Written files", self.written),
            ("Unsupported formatting", self.unsupported),
            ("Removed content", self.removed),
            ("Contact-line warnings", self.contacts),
        )
        lines = ["Print tagging review report", ""]
        for title, items in groups:
            if not items:
                continue
            lines.append(f"{title}:")
            lines.extend(f"- {item}" for item in items)
            lines.append("")
        lines.append(f"Result: {len(self.written)} written, {self.failed} failed.")
        return "\n".join(lines) + "\n"


class OutputWriter:
    """Manifest-backed writer that refuses to replace another story's file."""

    def __init__(self, output_dir: Path = OUTPUT_DIR):
        self.output_dir = output_dir
        self.manifest_path = output_dir / "manifest.json"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.data = {"version": 1, "files": {}}
        if self.manifest_path.exists():
            try:
                loaded = json.loads(self.manifest_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict) and isinstance(loaded.get("files"), dict):
                    self.data = loaded
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Cannot read output manifest: {exc}") from exc

    @staticmethod
    def _same_story(entry: dict, identity: dict) -> bool:
        return bool(
            entry
            and (
                (identity.get("post_id") and entry.get("post_id") == identity.get("post_id"))
                or (identity.get("wp_url") and entry.get("wp_url") == identity.get("wp_url"))
                or (identity.get("notion_id") and entry.get("notion_id") == identity.get("notion_id"))
            )
        )

    def write(self, stem: str, text: str, identity: dict) -> Path:
        filename = f"{stem}.txt"
        path = self.output_dir / filename
        entry = self.data["files"].get(filename)
        if entry and not self._same_story(entry, identity):
            raise FileExistsError(f"manifest maps {filename} to a different story")
        if path.exists() and not entry:
            raise FileExistsError(f"{filename} already exists but is not in the output manifest")
        safe = _macroman_safe(text)
        # A replace is only used after the manifest identifies this as the same
        # story, so reruns are safe while collisions remain non-destructive.
        temporary = path.with_suffix(".txt.tmp")
        temporary.write_text(safe, encoding="mac_roman", errors="strict")
        os.replace(temporary, path)
        self.data["files"][filename] = identity
        temporary_manifest = self.manifest_path.with_suffix(".json.tmp")
        temporary_manifest.write_text(json.dumps(self.data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary_manifest, self.manifest_path)
        return path


def _resolve_authors(row: dict | None, wp_data: dict) -> list[tuple[str, str]]:
    authors = parse_writer_title(row.get("Writer / Title")) if row else []
    authors = [(name.strip(), position.strip()) for name, position in authors if str(name).strip()]
    if authors:
        return authors
    creators = wp_data.get("parsely", {}).get("meta", {}).get("creator", [])
    return [(str(name).strip(), "") for name in creators if str(name).strip()]


def _artifact(row: dict | None, wp_url: str, paper_date: str) -> tuple[str, str, dict, ConversionNotes]:
    if row is None:
        raise ValueError("no Notion row found; cannot determine print filename")
    stem = filename_stem_from_row(row, paper_date)
    section = section_from_row(row)
    writer_error = writer_title_error(row.get("Writer / Title"))
    if writer_error:
        raise ValueError(f"malformed Writer / Title: {writer_error}")
    post_id = post_id_from_url(wp_url)
    data = fetch_post(post_id)
    headline = _clean_headline(data.get("title", {}).get("rendered", ""))
    if not headline:
        raise ValueError("missing WordPress title")
    authors = _resolve_authors(row, data)
    if not authors:
        raise ValueError("missing author in both Notion Writer / Title and WordPress")
    notes = ConversionNotes()
    dropcap_tags = {
        "arts & life": "@A&Ldropcap",
        "arts and life": "@A&Ldropcap",
        "the grind": "@GRIdropcap",
        "grind": "@GRIdropcap",
        "humor": "@HUMdropcap",
    }
    body = html_to_xquark(
        data.get("content", {}).get("rendered", ""),
        notes,
        dropcap_tag=dropcap_tags.get((section or "").strip().lower()),
    )
    identity = {"post_id": str(post_id), "wp_url": wp_url, "notion_id": row.get("id")}
    return stem, build_xquark(headline, section, authors, body), identity, notes


def convert_row(row: dict, paper_date: str) -> tuple[str, str]:
    """Compatibility helper: convert a Notion row without writing output."""
    wp_url = row.get("WP Post")
    if not wp_url:
        raise ValueError(f"Row {row.get('id')} has no WP Post URL")
    stem, text, _, _ = _artifact(row, wp_url, paper_date)
    return stem, text


def _write_report(report: ReviewReport, output_dir: Path | None = None) -> Path:
    output_dir = output_dir or OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "review-report.txt"
    rendered = report.render()
    path.write_text(_macroman_safe(rendered), encoding="mac_roman", errors="strict")
    print(rendered, end="")
    return path


def batch(paper_date: str) -> int:
    report = ReviewReport()
    try:
        from notion_api import paper_date_digits

        paper_date = paper_date_digits(paper_date)
    except ValueError as exc:
        report.issue("malformed", str(exc), failed=True)
        _write_report(report)
        return 1
    try:
        rows, community_rows = get_batch_rows()
    except Exception as exc:
        report.issue("malformed", f"Notion query failed: {exc}", failed=True)
        _write_report(report)
        print(f"Notion query failed; see {REPORT_PATH}", file=sys.stderr)
        return 1
    for row in community_rows:
        label = str(row.get("Slug (Print)") or row.get("id") or "unknown row")
        report.skipped.append(f"{label}: From the Community article (not batched).")
    if not rows:
        report.skipped.append("No non-Community rows matched the configured batch selection.")
        _write_report(report)
        print("No eligible rows. See OUTPUT/review-report.txt")
        return 0
    try:
        writer = OutputWriter(OUTPUT_DIR)
    except Exception as exc:
        report.issue("malformed", str(exc), failed=True)
        _write_report(report)
        return 1

    # Detect duplicate print slugs before fetching or writing either article.
    claims: dict[str, list[dict]] = {}
    for row in rows:
        try:
            stem = filename_stem_from_row(row, paper_date)
        except ValueError:
            # The per-row conversion below records missing section, slug, or
            # date metadata in Do manually.
            continue
        claims.setdefault(stem.casefold(), []).append(row)
    duplicates = {id(row) for same in claims.values() if len(same) > 1 for row in same}

    for row in rows:
        label = str(row.get("Slug (Print)") or row.get("Slug (Online)") or "unknown row")
        if id(row) in duplicates:
            report.issue("collisions", f"{label}: duplicate Slug (Print) in this batch", failed=True)
            continue
        if not row.get("Slug (Print)"):
            report.issue("malformed", f"{label}: missing Slug (Print)", failed=True)
            continue
        wp_url = row.get("WP Post")
        if not wp_url:
            report.issue("malformed", f"{label}: missing WP Post URL", failed=True)
            continue
        try:
            stem, text, identity, notes = _artifact(row, wp_url, paper_date)
            path = writer.write(stem, text, identity)
            report.written.append(path.name)
            report.include_notes(label, notes)
            if (section_from_row(row) or "").strip().lower().startswith("opinion"):
                report.unsupported.append(f"{label}: Opinions exported in standard form; review any special Opinion layout.")
        except FileExistsError as exc:
            report.issue("collisions", f"{label}: {exc}", failed=True)
        except Exception as exc:
            report.issue("malformed", f"{label}: {exc}", failed=True)
    _write_report(report)
    print(f"Done: {len(report.written)} written, {report.failed} failed. See {REPORT_PATH}")
    return 1 if report.failed else 0


def single(wp_url: str, paper_date: str) -> int:
    report = ReviewReport()
    try:
        from notion_api import paper_date_digits

        paper_date = paper_date_digits(paper_date)
        # Validate before a Notion lookup so malformed URLs have a useful error.
        post_id_from_url(wp_url)
        row = find_row_for_url(wp_url)
        writer = OutputWriter(OUTPUT_DIR)
        stem, text, identity, notes = _artifact(row, wp_url, paper_date)
        path = writer.write(stem, text, identity)
        report.written.append(path.name)
        report.include_notes(stem, notes)
        if not row:
            report.skipped.append("No Notion row matched this URL; used WordPress title/authors and NEWS template.")
        elif (section_from_row(row) or "").strip().lower().startswith("opinion"):
            report.unsupported.append(f"{stem}: Opinions exported in standard form; review any special Opinion layout.")
    except FileExistsError as exc:
        report.issue("collisions", str(exc), failed=True)
    except Exception as exc:
        report.issue("malformed", str(exc), failed=True)
    _write_report(report)
    if report.failed:
        print(f"Export failed; see {REPORT_PATH}", file=sys.stderr)
        return 1
    print(f"Written to OUTPUT/{report.written[0]}; see {REPORT_PATH}")
    return 0


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export Notion print stories as XQuark text.")
    parser.add_argument("--publication-date", required=True, metavar="D|DD", help="paper publication day for this export")
    parser.add_argument("wp_url", nargs="?", help="optional WordPress admin URL for a one-story re-export")
    args = parser.parse_args(argv)
    return single(args.wp_url, args.publication_date) if args.wp_url else batch(args.publication_date)


if __name__ == "__main__":
    raise SystemExit(cli())
