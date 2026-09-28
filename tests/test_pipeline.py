"""Offline regression tests for the print tagging rules."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from html_to_xquark import ConversionNotes, html_to_xquark
from main import OutputWriter, batch
from notion_api import PRINT_STATUS_FILTER, PRINT_WEEK_FILTER, get_batch_rows, parse_writer_title
from wp_to_xquark import build_xquark, fetch_post


class HtmlConversionTests(unittest.TestCase):
    def test_inline_lists_contact_and_removed_content(self):
        notes = ConversionNotes()
        output = html_to_xquark(
            "<p><strong>Bold <em>both</em></strong> — class of ’26… &amp; more</p>"
            "<ol><li>One</li><li><em>Two</em></li></ol>"
            "<ul><li>Three</li></ul>"
            "<p>Correction: old copy</p><figure><img src=x><figcaption>cap</figcaption></figure>"
            "<p>Contact Jane Doe at jane@stanford.edu.</p>",
            notes,
        )
        self.assertIn("<@CEBold>Bold <@$p><@CEBoldital>both<@$p>", output)
        self.assertIn("<\\#213>26", output)
        self.assertIn("<\\p><\\_><\\p>", output)
        self.assertIn("@DigitIndent:1. <\\i><@normalcopy>One", output)
        self.assertIn("@Bullet indent:<@Bullet>", output)
        self.assertIn("@@line:Contact Jane Doe", output)
        self.assertNotIn("<p>", output)
        self.assertNotIn("Correction: old copy", output)
        self.assertTrue(any("figure" in item for item in notes.removed))

    def test_no_empty_bysub_and_complete_section_headers(self):
        text = build_xquark("A title", "The Grind", [("One", "Editor"), ("Two", "")], "Copy")
        self.assertTrue(text.startswith("<v9.30><e0>\n@NewsHeader:ARTS & LIFE"))
        self.assertIn("@A&Lbyline:By ONE\n@A&Lbysub:EDITOR\n@A&Lbyline:By TWO", text)
        self.assertNotIn("@A&Lbysub:\n", text)


class MetadataAndOutputTests(unittest.TestCase):
    def test_author_variants(self):
        self.assertEqual(parse_writer_title("A / Editor, B / Writer"), [("A", "Editor"), ("B", "Writer")])
        self.assertEqual(parse_writer_title(["A", "B"]), [("A", ""), ("B", "")])
        self.assertEqual(parse_writer_title("A Writer/Story title"), [("A Writer", "")])

    def test_community_rows_are_not_batched(self):
        ordinary = {"id": "ordinary", "Writer / Title": "A Writer", "Print Week": PRINT_WEEK_FILTER, "Print Status": PRINT_STATUS_FILTER, "Web Status": "Finaled & published"}
        community = {"id": "community", "Writer / Title": "From the Community", "Print Week": PRINT_WEEK_FILTER, "Print Status": PRINT_STATUS_FILTER, "Web Status": "Finaled & published"}
        not_ready = {"id": "not-ready", "Writer / Title": "Other", "Web Status": "Draft"}
        with patch("notion_api.get_all_rows", return_value=[ordinary, community, not_ready]):
            self.assertEqual(get_batch_rows(), ([ordinary], [community]))

    def test_manifest_allows_rerun_but_blocks_another_story(self):
        with tempfile.TemporaryDirectory() as temporary:
            writer = OutputWriter(Path(temporary))
            identity = {"post_id": "1", "wp_url": "?p=1", "notion_id": "a"}
            writer.write("STORY", "plain", identity)
            writer.write("STORY", "updated", identity)
            with self.assertRaises(FileExistsError):
                writer.write("STORY", "other", {"post_id": "2", "wp_url": "?p=2", "notion_id": "b"})
            self.assertEqual((Path(temporary) / "STORY.txt").read_text(encoding="mac_roman"), "updated")

    def test_output_is_macroman_compatible(self):
        with tempfile.TemporaryDirectory() as temporary:
            writer = OutputWriter(Path(temporary))
            path = writer.write("ACCENT", "café and 🙂", {"post_id": "1"})
            self.assertEqual(path.read_bytes().decode("mac_roman"), "café and ?")

    def test_batch_reports_missing_slug_as_a_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            row = {"id": "bad", "WP Post": "https://example.test/?p=1"}
            with patch("main.OUTPUT_DIR", output), patch("main.get_batch_rows", return_value=([row], [])):
                self.assertEqual(batch(), 1)
            report = (output / "review-report.txt").read_text(encoding="mac_roman")
            self.assertIn("missing Slug (Print)", report)
            self.assertIn("Result: 0 written, 1 failed.", report)

    def test_batch_reports_community_article_as_skipped(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            community = {"id": "community", "Slug (Print)": "COMMUNITY"}
            with patch("main.OUTPUT_DIR", output), patch("main.get_batch_rows", return_value=([], [community])):
                self.assertEqual(batch(), 0)
            report = (output / "review-report.txt").read_text(encoding="mac_roman")
            self.assertIn("Do manually:", report)
            self.assertIn("COMMUNITY: From the Community article (not batched).", report)

    def test_report_puts_skips_and_failures_in_do_manually_first(self):
        from main import ReviewReport

        report = ReviewReport(written=["done.txt"], skipped=["community"], malformed=["missing URL"], collisions=["duplicate slug"])
        rendered = report.render()
        self.assertLess(rendered.index("Do manually:"), rendered.index("Written files:"))
        self.assertIn("- community", rendered)
        self.assertIn("- missing URL", rendered)
        self.assertIn("- duplicate slug", rendered)

    def test_clean_report_omits_empty_sections(self):
        from main import ReviewReport

        rendered = ReviewReport(written=["STORY.txt"]).render()
        self.assertIn("Written files:\n- STORY.txt", rendered)
        self.assertNotIn("Do manually:", rendered)
        self.assertNotIn("Unsupported formatting:", rendered)

    def test_unavailable_wordpress_post_requires_manual_handling(self):
        class Response:
            status_code = 404

        with patch("wp_to_xquark.requests.get", return_value=Response()):
            with self.assertRaisesRegex(RuntimeError, "Add it manually"):
                fetch_post("1298172")


if __name__ == "__main__":
    unittest.main()
