"""Offline regression tests for the print tagging rules."""

import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from html_to_xquark import ConversionNotes, html_to_xquark
from main import OutputWriter, ReviewReport, _write_report, batch, cli
from notion_api import PRINT_STATUS_FILTER, PRINT_WEEK_FILTER, filename_stem_from_row, get_batch_rows, parse_writer_title, writer_title_error
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

    def test_first_paragraph_is_tabbed(self):
        output = html_to_xquark("<p>First paragraph.</p><p>Second paragraph.</p>")
        self.assertEqual(output, "\tFirst paragraph.\n\tSecond paragraph.")

    def test_headings_are_standalone_bold_paragraphs(self):
        output = html_to_xquark("<p>Before.</p><h2><em>A heading</em></h2><h4>Another heading</h4><p>After.</p>")
        self.assertEqual(
            output,
            "\tBefore.\n\t<@CEBold>A heading<@$p>\n\t<@CEBold>Another heading<@$p>\n\tAfter.",
        )

    def test_no_empty_bysub_and_complete_section_headers(self):
        text = build_xquark("A title", "The Grind", [("One", "Editor"), ("Two", "")], "Copy")
        self.assertTrue(text.startswith("<v9.30><e0>\n@NewsHeader:ARTS & LIFE"))
        self.assertIn("@A&Lbyline:By ONE\n@A&Lbysub:editor\n@A&Lbyline:By TWO", text)
        self.assertNotIn("@A&Lbysub:\n", text)
        self.assertNotIn("@headline:", text)

    def test_normalcopy_follows_leading_italic_note(self):
        text = build_xquark(
            "A title",
            "Arts & Life",
            [("One", "Editor")],
            "<@CEIt>\t Editor’s Note: context.<@$p>\n<@A&Ldropcap>Story copy.",
        )
        self.assertIn(
            "<@CEIt>\t Editor’s Note: context.<@$p>\n@normalcopy:<@A&Ldropcap>Story copy.",
            text,
        )

    def test_dropcap_skips_opening_italic_note(self):
        output = html_to_xquark(
            "<p><em>Editor’s Note: context.</em></p><p>“This is the story.</p><p>Second paragraph.</p>",
            dropcap_tag="@A&Ldropcap",
        )
        self.assertTrue(output.startswith("<@CEIt>\t Editor’s Note: context.<@$p>"))
        self.assertIn("\n<@A&Ldropcap><*bn(7.2,1,0)*d(2,6)>“T<@$p>his", output)
        self.assertIn("<*d(0)> Second paragraph.", output)

    def test_non_al_body_does_not_receive_dropcap(self):
        output = html_to_xquark("<p>News copy.</p>")
        self.assertNotIn("A&Ldropcap", output)

    def test_section_specific_dropcap_tags_and_reset_are_supported(self):
        output = html_to_xquark("<p>Grind copy.</p><p>Next paragraph.</p>", dropcap_tag="@GRIdropcap")
        self.assertIn("<@GRIdropcap><*bn(7.2,1,0)*d(1,6)>G<@$p>rind", output)
        self.assertIn("<*d(0)> Next paragraph.", output)

    def test_opinion_dropcap_uses_opinion_style(self):
        output = html_to_xquark(
            "<p>“This is an opinion.</p><p>Second paragraph.</p>",
            opinion_dropcap=True,
        )
        self.assertTrue(output.startswith("<*d(2,3)><z9>“T<z$>his is an opinion."))
        self.assertIn("\n\t<*d(0)> Second paragraph.", output)


class MetadataAndOutputTests(unittest.TestCase):
    def test_author_variants(self):
        self.assertEqual(parse_writer_title("A / Editor, B / Writer"), [("A", "Editor"), ("B", "Writer")])
        self.assertEqual(parse_writer_title(["A", "B"]), [("A", ""), ("B", "")])
        self.assertEqual(parse_writer_title("A Writer/Story title"), [("A Writer", "")])

    def test_malformed_writer_title_is_flagged(self):
        self.assertEqual(writer_title_error("A/Writer"), "use spaces around each slash: Name / Role")
        self.assertEqual(
            writer_title_error("A / Writer and B / Editor"),
            "separate multiple Name / Role pairs with commas, not 'and'",
        )
        self.assertIsNone(writer_title_error("A / Writer, B / Editor"))

    def test_filename_uses_section_lowercase_slug_and_publication_date(self):
        row = {"Section": "Sports", "Slug (Print)": "Home Opener"}
        self.assertEqual(filename_stem_from_row(row, "28"), "SPOhome opener28")

    def test_cli_passes_publication_date_to_batch(self):
        with patch("main.batch", return_value=0) as run_batch:
            self.assertEqual(cli(["--publication-date", "28"]), 0)
        run_batch.assert_called_once_with("28")

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
                self.assertEqual(batch("28"), 1)
            report = (output / "review-report.txt").read_text(encoding="mac_roman")
            self.assertIn("missing Slug (Print)", report)
            self.assertIn("Result: 0 written, 1 failed.", report)

    def test_batch_reports_malformed_writer_title_for_manual_handling(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            row = {
                "id": "bad-writer",
                "Section": "News",
                "Slug (Print)": "BAD",
                "Writer / Title": "A / Writer and B / Editor",
                "WP Post": "https://example.test/?p=1",
            }
            with patch("main.OUTPUT_DIR", output), patch("main.get_batch_rows", return_value=([row], [])):
                self.assertEqual(batch("28"), 1)
            report = (output / "review-report.txt").read_text(encoding="mac_roman")
            self.assertIn("Do manually:", report)
            self.assertIn("malformed Writer / Title", report)

    def test_batch_reports_community_article_as_skipped(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            community = {"id": "community", "Slug (Print)": "COMMUNITY"}
            with patch("main.OUTPUT_DIR", output), patch("main.get_batch_rows", return_value=([], [community])):
                self.assertEqual(batch("28"), 0)
            report = (output / "review-report.txt").read_text(encoding="mac_roman")
            self.assertIn("Do manually:", report)
            self.assertIn("COMMUNITY: From the Community article (not batched).", report)

    def test_report_puts_skips_and_failures_in_do_manually_first(self):
        report = ReviewReport(written=["done.txt"], skipped=["community"], malformed=["missing URL"], collisions=["duplicate slug"])
        rendered = report.render()
        self.assertLess(rendered.index("Do manually:"), rendered.index("Written files:"))
        self.assertIn("- community", rendered)
        self.assertIn("- missing URL", rendered)
        self.assertIn("- duplicate slug", rendered)

    def test_clean_report_omits_empty_sections(self):
        rendered = ReviewReport(written=["STORY.txt"]).render()
        self.assertIn("Written files:\n- STORY.txt", rendered)
        self.assertNotIn("Do manually:", rendered)
        self.assertNotIn("Unsupported formatting:", rendered)

    def test_report_is_written_and_printed(self):
        with tempfile.TemporaryDirectory() as temporary, patch("sys.stdout", new_callable=StringIO) as stdout:
            _write_report(ReviewReport(written=["STORY.txt"]), Path(temporary))
        self.assertIn("Written files:\n- STORY.txt", stdout.getvalue())

    def test_unavailable_wordpress_post_requires_manual_handling(self):
        class Response:
            status_code = 404

        with patch("wp_to_xquark.requests.get", return_value=Response()):
            with self.assertRaisesRegex(RuntimeError, "Add it manually"):
                fetch_post("1298172")


if __name__ == "__main__":
    unittest.main()
