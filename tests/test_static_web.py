"""Bounded local web source validation without executing a family or browser."""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sheepfling_styling.static_web import StaticWebError, validate_static_web
from sheepfling_styling.typography_roles import SHARED_TYPE_ROLES, css_role_definitions


def fixture_sources(root: Path) -> dict:
    """Write a family-neutral local site with shared semantic selector coverage."""
    web = root / "web"
    web.mkdir(exist_ok=True)
    (web / "assets").mkdir(exist_ok=True)
    (web / "index.html").write_text('''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sample system</title><link rel="stylesheet" href="styles.css"></head><body>
<header><a href="#main">Skip to content</a><nav aria-label="Primary"><a href="#process">Process</a></nav></header>
<main id="main"><h1 data-type="document.title">A clear premise</h1><section id="process"><h2>Process</h2>
<p data-type="body">Literal &amp; 50% #1_ remains plain copy.</p><img src="assets/mark.svg" alt="">
<a href="assets/brief.pdf" download>Download the brief</a></section></main><footer>Sample footer</footer>
</body></html>''', encoding="utf-8")
    (web / "styles.css").write_text(
        ':root {--face-body: "Sample Local", sans-serif;}\n'
        + css_role_definitions({role: "body" for role in SHARED_TYPE_ROLES}, {"body", "display", "strong"})
        + '\na:focus-visible {outline: 2px solid currentColor;}\n'
        + '@media (max-width: 48rem) {main {display: block;}}\n'
        + '@media (prefers-reduced-motion: reduce) {* {scroll-behavior: auto;}}\n', encoding="utf-8")
    (web / "assets/mark.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4"/></svg>', encoding="utf-8")
    (web / "assets/brief.pdf").write_bytes(b"%PDF-1.7\nsynthetic linked document; no rendering claims\n")
    def record(name):
        return {"path": "web/" + name, "sha256": hashlib.sha256((web / name).read_bytes()).hexdigest()}
    return {"schema_version": "0.1.0", "id": "web-light", "context": "light", "palette": "paper",
            "entry": record("index.html"), "dependencies": [record(name) for name in ("styles.css", "assets/mark.svg", "assets/brief.pdf")],
            "required_text": ["editorial.lines.0", "editorial.body"],
            "viewports": [{"width": 390, "height": 844}, {"width": 768, "height": 1024}, {"width": 1440, "height": 1000}]}


class StaticWebTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.web = fixture_sources(self.root)
        self.copy = {"editorial.lines.0": "A clear premise", "editorial.body": "Literal & 50% #1_ remains plain copy."}

    def tearDown(self):
        self.directory.cleanup()

    def validate(self):
        return validate_static_web(self.web, self.root, {"paper": {}}, self.copy, {role: "body" for role in SHARED_TYPE_ROLES})

    def replace(self, name, before, after):
        path = self.root / "web" / name
        path.write_text(path.read_text().replace(before, after), encoding="utf-8")
        self.repin()

    def repin(self):
        for record in [self.web["entry"], *self.web["dependencies"]]:
            path = self.root / record["path"]
            if path.is_file():
                record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()

    def test_static_metadata_preserves_exact_sources_without_browser_claims(self):
        plan = self.validate()
        self.assertEqual(plan["entry"], "index.html")
        self.assertEqual(plan["files"]["index.html"], (self.root / "web/index.html").read_bytes())
        self.assertEqual(plan["checks"]["shared_type_role_selectors"], 17)
        self.assertEqual(plan["checks"]["browser_review"], "pending")
        pdf = next(source for source in plan["sources"] if source["path"].endswith(".pdf"))
        self.assertEqual(pdf["representation"], "linked-pdf-document")
        self.assertFalse(pdf["editable"])
        self.assertNotIn("page_count", pdf)

    def test_declaration_is_versioned_closed_and_viewports_are_finite(self):
        original = deepcopy(self.web)
        for mutate in (
            lambda web: web.update(schema_version="9.0.0"),
            lambda web: web.update(extra=True),
            lambda web: web.update(palette=[]),
            lambda web: web.update(viewports=[]),
            lambda web: web["viewports"][0].update(width=True),
            lambda web: web["viewports"][0].update(height=float("inf")),
            lambda web: web["viewports"][2].update(width=768),
            lambda web: web.update(required_text=["editorial.body", "editorial.body"]),
        ):
            self.web = deepcopy(original)
            mutate(self.web)
            with self.subTest(web=self.web), self.assertRaises(StaticWebError):
                self.validate()

    def test_hash_paths_symlinks_duplicates_and_code_dependencies_reject(self):
        original = deepcopy(self.web)
        for name in ("../outside.html", "/absolute.html", "web/./index.html", "web//index.html", "web\\index.html"):
            self.web = deepcopy(original)
            self.web["entry"]["path"] = name
            with self.subTest(name=name), self.assertRaises(StaticWebError):
                self.validate()
        self.web = deepcopy(original)
        self.web["entry"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(StaticWebError, "hash differs"):
            self.validate()
        self.web = deepcopy(original)
        self.web["dependencies"].append(deepcopy(self.web["dependencies"][0]))
        with self.assertRaisesRegex(StaticWebError, "unique"):
            self.validate()
        self.web = deepcopy(original)
        self.web["dependencies"][0]["path"] = "web/app.js"
        with self.assertRaisesRegex(StaticWebError, "executable code"):
            self.validate()
        self.web = deepcopy(original)
        (self.root / "web/linked.css").symlink_to(self.root / "web/styles.css")
        self.web["dependencies"][0]["path"] = "web/linked.css"
        with self.assertRaisesRegex(StaticWebError, "symlink"):
            self.validate()

    def test_html_structure_copy_and_local_targets_are_checked(self):
        original = (self.root / "web/index.html").read_text()
        for before, after in (
            ('lang="en"', ''), ('<main id="main">', '<div id="main">'),
            ('<h1 data-type="document.title">', '<h1 data-type="unknown">'),
            ('A clear premise', 'A different premise'), ('href="#process"', 'href="#missing"'),
            ('src="assets/mark.svg"', 'src="https://example.com/mark.svg"'),
            ('<meta charset="utf-8">', '<meta http-equiv="refresh" content="0;url=https://example.com">'),
            ('<footer>', '<script>alert(1)</script><footer>'),
            ('alt=""', ''), ('<header>', '<header style="color:red">'),
            ('href="#process"', 'href="index.html#missing"'),
            ('<footer>', '<svg><animate attributeName="href" to="https://example.com/a.png"></animate></svg><footer>'),
            ('<footer>', '<svg><rect fill="url(https://example.com/paint.svg)"></rect></svg><footer>'),
        ):
            (self.root / "web/index.html").write_text(original, encoding="utf-8")
            self.replace("index.html", before, after)
            with self.subTest(after=after), self.assertRaises(StaticWebError):
                self.validate()

    def test_only_linked_css_can_satisfy_semantic_and_interaction_signals(self):
        original = (self.root / "web/styles.css").read_text()
        for before, after in (
            ('[data-type="caption"]', '.unshared-caption'),
            (':focus-visible', ':hover'), ('max-width:', 'width:'),
            ('prefers-reduced-motion', 'prefers-color-scheme'),
            ('--face-body: "Sample Local"', 'background-image: url("https://example.com/image.png")'),
            ('[data-type="caption"] {font-family: var(--face-body);}', '[data-type="caption"] {font-family: serif;}'),
        ):
            (self.root / "web/styles.css").write_text(original, encoding="utf-8")
            self.replace("styles.css", before, after)
            with self.subTest(after=after), self.assertRaises(StaticWebError):
                self.validate()
        (self.root / "web/unused.css").write_text(original, encoding="utf-8")
        self.web["dependencies"].append({"path": "web/unused.css", "sha256": ""})
        (self.root / "web/styles.css").write_text('body {color: black;}', encoding="utf-8")
        self.repin()
        with self.assertRaisesRegex(StaticWebError, "17 shared"):
            self.validate()

    def test_svg_pdf_and_disguised_font_bytes_are_classified_truthfully(self):
        path = self.root / "web/assets/mark.svg"
        original = path.read_bytes()
        for raw in (b"not SVG", b"<svg><script>bad()</script></svg>",
                    b'<svg><image href="https://example.com/image.png"/></svg>', b"OTTOdisguised-font",
                    b'<svg><animate attributeName="href" to="https://example.com/a.png"/></svg>',
                    b'<svg><set attributeName="href" to="https://example.com/a.png"/></svg>'):
            path.write_bytes(raw)
            self.repin()
            with self.subTest(raw=raw), self.assertRaises(StaticWebError):
                self.validate()
        path.write_bytes(original)
        (self.root / "web/assets/brief.pdf").write_bytes(b"not PDF")
        self.repin()
        with self.assertRaisesRegex(StaticWebError, "PDF bytes"):
            self.validate()

    def test_text_sources_have_a_bounded_size_before_reading(self):
        (self.root / "web/styles.css").write_bytes(b" " * 1_048_577)
        with self.assertRaisesRegex(StaticWebError, "bounded file limit"):
            self.validate()


if __name__ == "__main__":
    unittest.main()
