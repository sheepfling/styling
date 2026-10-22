"""Trusted native TeX retains its composition while joining shared proof checks."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from PIL import ImageCms

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sheepfling_styling.native_tex import NativeTexError, build, validate_manifest


def pin(root: Path, name: str, raw: bytes) -> dict[str, str]:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {"path": name, "sha256": hashlib.sha256(raw).hexdigest()}


class NativeTexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        profile = pin(self.root, "assets/sRGB.icc", icc)
        tex = r"""\documentclass{article}
\usepackage[letterpaper,margin=60pt]{geometry}
\usepackage{fontspec}
\begin{document}
\special{pdf:fstream @ProofSRGB (assets/sRGB.icc) << /N 3 >>}
\special{pdf:put @catalog << /OutputIntents [ << /Type /OutputIntent /S /GTS_PDFA1 /OutputConditionIdentifier (sRGB IEC61966-2.1) /DestOutputProfile @ProofSRGB >> ] >>}
\fontsize{26}{32}\selectfont A distinct native page
\end{document}
""".encode()
        entry = pin(self.root, "layout/main.tex", tex)
        self.manifest = {"schema_version": "0.1.0", "family_id": "sample-family", "source_state": "selected-for-now",
                         "route": "native-layout", "sources": [entry, profile], "srgb_icc": profile,
                         "outputs": [{"id": "one-page", "slot": "document-one-page", "context": "light", "entry": entry,
                                      "page_count": 1, "page_pt": [612, 792], "required_text": ["A distinct native page"], "passes": 1}]}
        self.manifest_path = self.root / "manifest.json"
        self.write()

    def tearDown(self):
        self.temp.cleanup()

    def write(self):
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_source_hash_and_selection_gate(self):
        self.assertEqual(validate_manifest(self.manifest_path)["manifest"]["family_id"], "sample-family")
        self.manifest["source_state"] = "proposed-unselected"
        self.write()
        with self.assertRaisesRegex(NativeTexError, "cannot claim baseline"):
            validate_manifest(self.manifest_path)
        self.manifest["source_state"] = "selected-for-now"
        self.manifest["sources"][0]["sha256"] = "0" * 64
        self.write()
        with self.assertRaisesRegex(NativeTexError, "bytes differ"):
            validate_manifest(self.manifest_path)

    @unittest.skipUnless(all(shutil.which(tool) for tool in ("xelatex", "pdftotext", "pdffonts", "pdftoppm")),
                         "native TeX and Poppler tools are needed")
    def test_historical_web_source_stays_source_only(self):
        html = pin(self.root, "web/index.html", b"<html><link rel='stylesheet' href='styles.css'><body>sample</body></html>")
        css = pin(self.root, "web/styles.css", b"body { color: navy; }")
        self.manifest["sources"].extend([html, css])
        self.manifest["web_source"] = {"entry": html, "dependencies": [css]}
        self.write()
        report = build(self.manifest_path, self.root / "web-output")
        self.assertEqual(report["coverage"]["web-light"]["status"], "source-only")
        self.assertEqual(report["web_source"]["browser_review"], "pending")
        self.assertEqual((self.root / "web-output/source/web/index.html").read_bytes(),
                         (self.root / "web/index.html").read_bytes())

    @unittest.skipUnless(all(shutil.which(tool) for tool in ("xelatex", "pdftotext", "pdffonts", "pdftoppm")),
                         "native TeX and Poppler tools are needed")
    def test_native_composition_builds_without_template_replacement(self):
        report = build(self.manifest_path, self.root / "output")
        self.assertEqual(report["outputs"][0]["status"], "built-awaiting-visual-review")
        self.assertEqual(report["coverage"]["document-one-page"]["outputs"], ["one-page"])
        self.assertEqual(report["coverage"]["web-light"]["status"], "not-run")
        self.assertEqual((self.root / "output/source/layout/main.tex").read_bytes(),
                         (self.root / "layout/main.tex").read_bytes())
        self.assertEqual(len(report["outputs"][0]["previews"]), 1)


if __name__ == "__main__":
    unittest.main()
