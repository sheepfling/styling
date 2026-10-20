"""Family typography outputs must consume the family content manifest."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = ROOT / "scripts/build_family_typesetting_suite.py"
SPEC = importlib.util.spec_from_file_location("family_typesetting_builder", BUILDER_PATH)
BUILDER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(BUILDER)


def sample_content():
    """Neutral, synthetic content for exercising the shared layout builder."""
    return {
        "title": "Shared layout sample",
        "subtitle": "One structure, several output shapes",
        "lead": "A short synthetic summary used only by unit tests.",
        "sections": [
            {"title": "First section", "paragraphs": ["Sample copy for the first section."]},
            {"title": "Second section", "paragraphs": ["Sample copy for the second section."]},
            {"title": "Third section", "paragraphs": ["Sample copy for the third section."]},
        ],
        "table": {"caption": "Synthetic component table", "columns": ["A", "B", "C"], "column_widths": [.2, .3, .5],
                  "rows": [["One", "Two", "Three"] for _ in range(4)]},
        "figure": {"caption": "Synthetic four-step flow", "steps": ["One", "Two", "Three", "Four"]},
        "cards": [
            {"kind": "NOTE", "title": "Note", "body": "Synthetic note."},
            {"kind": "CAUTION", "title": "Caution", "body": "Synthetic caution."},
            {"kind": "SPECIFICATION", "title": "Specification", "body": "Synthetic specification."},
            {"kind": "EXAMPLE", "title": "Example", "body": "Synthetic example."},
        ],
        "references": [{"title": "Synthetic source", "detail": "Test fixture only."}],
        "appendix": {"intro": "Synthetic appendix.", "items": ["No external source data."]},
        "footnote": "Synthetic footnote.",
        "one_page": {"heading": "Brief", "summary": "A synthetic one-page summary.", "facts": []},
        "product_slick": {"eyebrow": "SAMPLE", "title": "Sample feature", "subtitle": "Synthetic subtitle",
                          "description": "A synthetic description.", "highlights": [{"label": "Clear.", "text": "First."},
                          {"label": "Simple.", "text": "Second."}], "facts": [{"label": "Status", "value": "Test."},
                          {"label": "Scope", "value": "Synthetic."}], "next_step": "Review the test.", "source_note": "Synthetic fixture only."},
    }


class FamilyTypesettingContentTests(unittest.TestCase):
    def test_compact_outputs_use_caller_supplied_copy(self):
        content = sample_content()
        style = {
            "display_name": "Test Family",
            "status_label": "SPECIMEN",
            "note": "Test scope.",
            "accents": {"marker_type": "square-index", "marker": "01", "tag_shape": "square", "card_shape": "square"},
        }

        one_page = BUILDER.compact_document(style, content, "one-page")
        two_page = BUILDER.compact_document(style, content, "two-page")
        product_slick = BUILDER.compact_document(style, content, "product-slick")

        self.assertIn(content["one_page"]["summary"], one_page)
        self.assertIn(content["sections"][0]["title"], two_page)
        self.assertIn(content["product_slick"]["title"], product_slick)
        self.assertIn(content["product_slick"]["highlights"][0]["text"], product_slick)
        self.assertNotIn("Four formats, one content model", product_slick)

    def test_two_page_output_uses_all_three_sections(self):
        content = sample_content()
        style = {
            "display_name": "Test Family",
            "status_label": "SPECIMEN",
            "note": "Test scope.",
            "accents": {"marker_type": "square-index", "marker": "01", "tag_shape": "square", "card_shape": "square"},
        }
        source = BUILDER.compact_document(style, content, "two-page")
        for section in content["sections"]:
            self.assertIn(section["title"], source)

    def test_composed_one_page_uses_family_order_and_ui_states(self):
        content = sample_content()
        content.update({
            "title": "A little idea, clearly set",
            "subtitle": "A gecko absorbs powers.",
            "lead": "A friendly page makes the premise easy to enter.",
            "one_page": {"heading": "Brief", "summary": "Summary", "facts": [], "source_note": "Concept only."},
            "ui_components": {
                "tabs": [
                    {"label": "Collection", "state": "selected"},
                    {"label": "Game detail", "state": "unselected"},
                    {"label": "System", "state": "unselected"},
                ],
                "status_chips": [{"label": "C2 / LIGHT"}, {"label": "CONCEPT / OPEN"}],
                "panels": [
                    {"label": "Known", "title": "Premise", "body": "A little gecko absorbs powers.", "tone": "emphasis"},
                    {"label": "Open", "title": "Still to decide", "body": "The title and rules are not supplied.", "tone": "quiet"},
                ],
                "actions": [
                    {"label": "Collection", "kind": "secondary", "direction": "back"},
                    {"label": "Preview demo", "kind": "primary", "direction": "forward"},
                ],
            },
        })
        style = {
            "display_name": "Jellybean Games", "status_label": "C2 / LIGHT",
            "accents": {"tag_shape": "rounded", "card_shape": "rounded"},
            "one_page_composition": {
                "flow": ["navigation", "title", "subtitle", "lead", "status_chips", "panels", "actions", "source_note"],
                "panel_layout": "paired", "row_gap_mm": 4, "title_gap_mm": 2,
            },
        }

        source = BUILDER.compact_document(style, content, "one-page")
        self.assertLess(source.index("Collection"), source.index("A little idea, clearly set"))
        self.assertIn(r"\textbf{SELECTED}", source)
        self.assertIn(r"$\leftarrow$", source)
        self.assertIn(r"$\rightarrow$", source)
        self.assertIn("Game detail", source)
        self.assertIn("The title and rules are not supplied.", source)

    def test_composed_layout_rejects_ambiguous_selection(self):
        content = sample_content()
        content["ui_components"] = {
            "tabs": [{"label": "A", "state": "selected"}, {"label": "B", "state": "selected"}],
            "status_chips": [{"label": "OPEN"}],
            "panels": [{"label": "A", "title": "A", "body": "A"}, {"label": "B", "title": "B", "body": "B"}],
            "actions": [{"label": "Back", "kind": "secondary"}, {"label": "Next", "kind": "primary"}],
        }
        style = {
            "family_id": "test", "display_name": "Test Family", "profile_version": "0.1.0",
            "status": "test", "output_dir": "unused", "type": {"body": {}, "display": {}, "strong": {}},
            "colors": {"page": "#FFFFFF", "ink": "#111111", "muted": "#666666", "accent": "#008000"},
            "accents": {}, "sources": [],
            "role_map": {role: "body" for role in BUILDER.SHARED_TYPE_ROLES},
            "one_page_composition": {
                "flow": ["navigation", "title", "subtitle", "lead", "status_chips", "panels", "actions", "source_note"],
                "panel_layout": "paired",
            },
        }
        with self.assertRaisesRegex(BUILDER.BuildError, "exactly one selected state"):
            BUILDER.validate_manifest(style, content)

    def test_semantic_role_map_covers_the_shared_contract(self):
        content = sample_content()
        style = {
            "family_id": "test", "display_name": "Test Family", "profile_version": "0.1.0",
            "status": "test", "output_dir": "unused", "type": {"body": {}, "display": {}, "strong": {}},
            "colors": {"page": "#FFFFFF", "ink": "#111111", "muted": "#666666", "accent": "#008000"},
            "accents": {}, "sources": [],
            "role_map": {role: "body" for role in BUILDER.SHARED_TYPE_ROLES},
        }
        BUILDER.validate_manifest(style, content)
        style["role_map"].pop("caption")
        with self.assertRaisesRegex(BUILDER.BuildError, "every shared semantic type role"):
            BUILDER.validate_manifest(style, content)

    def test_font_source_hashes_are_checked_when_declared(self):
        content = sample_content()
        with tempfile.TemporaryDirectory() as directory:
            font = Path(directory) / "font.ttf"
            font.write_bytes(b"font bytes")
            style = {
                "family_id": "test", "display_name": "Test Family", "profile_version": "0.1.0",
                "status": "test", "output_dir": "unused",
                "type": {"body": {"path": str(font), "sha256": "0" * 64}, "display": {}, "strong": {}},
                "colors": {"page": "#FFFFFF", "ink": "#111111", "muted": "#666666", "accent": "#008000"},
                "accents": {}, "sources": [],
                "role_map": {role: "body" for role in BUILDER.SHARED_TYPE_ROLES},
            }
            with self.assertRaisesRegex(BUILDER.BuildError, "Font source hash differs"):
                BUILDER.validate_manifest(style, content)

    def test_srgb_verifier_resolves_catalog_and_compares_exact_profile_bytes(self):
        from PIL import ImageCms
        from pypdf import PdfWriter
        from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject, TextStringObject

        icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        profile = DecodedStreamObject()
        profile.set_data(icc)
        profile[NameObject("/N")] = NumberObject(3)
        profile_ref = writer._add_object(profile)
        intent = DictionaryObject({
            NameObject("/Type"): NameObject("/OutputIntent"),
            NameObject("/S"): NameObject("/GTS_PDFA1"),
            NameObject("/OutputConditionIdentifier"): TextStringObject("sRGB IEC61966-2.1"),
            NameObject("/DestOutputProfile"): profile_ref,
        })
        writer._root_object[NameObject("/OutputIntents")] = ArrayObject([writer._add_object(intent)])
        with tempfile.TemporaryDirectory() as directory:
            profile_path = Path(directory) / "expected.icc"
            profile_path.write_bytes(icc)
            candidate = Path(directory) / "intent.pdf"
            with candidate.open("wb") as stream:
                writer.write(stream)
            report = BUILDER.verify_srgb_output_intent(candidate, profile_path)
            self.assertEqual(report["output_condition"], "sRGB IEC61966-2.1")
            self.assertEqual(report["profile_components"], 3)
            self.assertEqual(report["profile_bytes"], len(icc))
            wrong = Path(directory) / "wrong.icc"
            wrong.write_bytes(icc[:-1] + bytes([icc[-1] ^ 1]))
            with self.assertRaisesRegex(BUILDER.BuildError, "does not match"):
                BUILDER.verify_srgb_output_intent(candidate, wrong)

    def test_srgb_verifier_rejects_a_pdf_without_a_catalog_intent(self):
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "no-intent.pdf"
            with candidate.open("wb") as stream:
                writer.write(stream)
            with self.assertRaisesRegex(BUILDER.BuildError, "exactly one catalog OutputIntent"):
                BUILDER.verify_srgb_output_intent(candidate)


if __name__ == "__main__":
    unittest.main()
