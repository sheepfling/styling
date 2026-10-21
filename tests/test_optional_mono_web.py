"""Optional physical mono faces must resolve in shared web role selectors."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("optional_mono_builder", ROOT / "scripts/build_family_typesetting_suite.py")
BUILDER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(BUILDER)


def sample_style():
    return {
        "display_name": "Synthetic Sample",
        "type": {"body": {"family": "Sample Body"}, "display": {"family": "Sample Display"},
                 "strong": {"family": "Sample Strong"}, "wordmark": {"family": "Sample Wordmark"}},
        "colors": {"page": "#FFFFFF", "ink": "#111111", "muted": "#555555", "accent": "#006633"},
        "accents": {},
        "role_map": {role: "body" for role in BUILDER.SHARED_TYPE_ROLES},
    }


def sample_content():
    return {
        "title": "A synthetic title", "subtitle": "A synthetic subtitle", "lead": "A brief summary.",
        "sections": [{"title": "Section", "paragraphs": ["Synthetic body copy."]}],
        "table": {"columns": ["Status"], "rows": [["Sample"]], "caption": "Sample table"},
        "cards": [{"kind": "NOTE", "title": "Sample note", "body": "Synthetic supporting copy."}],
        "product_slick": {"eyebrow": "SAMPLE", "title": "Sample feature", "subtitle": "Synthetic sample",
                          "description": "Sample description.", "highlights": [{"label": "Clear", "text": "Copy."}],
                          "source_note": "Synthetic source."},
        "one_page": {"summary": "Sample brief."},
        "figure": {"steps": ["One", "Two", "Three", "Four"], "caption": "Sample process"},
        "references": [{"title": "Synthetic reference", "detail": "Sample only."}],
        "appendix": {"intro": "Synthetic appendix."},
    }


class OptionalMonoWebTests(unittest.TestCase):
    def test_declared_local_mono_family_and_weight_resolve_role_variable(self):
        style = sample_style()
        style["type"]["mono"] = {"family": "Sample Mono", "weight": 500}
        style["role_map"]["label"] = style["role_map"]["annotation"] = "mono"
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "web"
            BUILDER.html_document(style, sample_content(), output, Path(temporary))
            css = (output / "styles.css").read_text(encoding="utf-8")
            self.assertIn('@font-face { font-family: MonoFace; src: local("Sample Mono"); font-weight: 500; }', css)
            self.assertIn('--mono:MonoFace, "Sample Mono", monospace;', css)
            self.assertIn('--role-label:var(--mono);', css)
            self.assertIn('--role-annotation:var(--mono);', css)
            self.assertEqual(BUILDER.verify_web_output(output)["shared_type_role_selectors"], 17)

    def test_explicit_mono_web_file_is_copied_and_web_weight_takes_precedence(self):
        style = sample_style()
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "sample-mono.woff2"
            source.write_bytes(b"synthetic-font-asset")
            style["type"]["mono"] = {"family": "Sample Mono", "web_file": str(source), "weight": 400, "web_weight": 600}
            style["role_map"]["label"] = "mono"
            output = Path(temporary) / "web"
            files = BUILDER.html_document(style, sample_content(), output, Path(temporary))
            css = (output / "styles.css").read_text(encoding="utf-8")
            self.assertIn('@font-face { font-family: MonoFace; src: url("assets/sample-mono.woff2"); font-weight: 600; }', css)
            self.assertIn("assets/sample-mono.woff2", files)
            self.assertEqual((output / "assets/sample-mono.woff2").read_bytes(), source.read_bytes())
            self.assertEqual(BUILDER.verify_web_output(output)["shared_type_role_selectors"], 17)

    def test_legacy_four_face_output_does_not_invent_mono(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "web"
            BUILDER.html_document(sample_style(), sample_content(), output, Path(temporary))
            css = (output / "styles.css").read_text(encoding="utf-8")
            self.assertEqual(css.count("@font-face"), 4)
            self.assertNotIn("MonoFace", css)
            self.assertNotIn("--mono:", css)
            self.assertIn('--body:BodyFace, "Sample Body", Georgia, serif;', css)
            self.assertIn('--role-label:var(--body);', css)


if __name__ == "__main__":
    unittest.main()
