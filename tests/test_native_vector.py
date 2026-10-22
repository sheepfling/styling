"""Native SVG families keep their own geometry and linked raster provenance."""
from __future__ import annotations

from io import BytesIO
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from PIL import Image
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sheepfling_styling.native_vector import NativeVectorError, build, validate_manifest
from sheepfling_styling.family_coverage import BASELINE_SLOTS


def pin(root: Path, path: Path, data: bytes) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"path": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(data).hexdigest()}


class NativeVectorTests(unittest.TestCase):
    def test_native_adapter_slots_track_the_shared_suite(self):
        adapter = json.loads((ROOT / "contracts/native-family-adapters.json").read_text())
        suite = json.loads((ROOT / "contracts/typography-deliverable-suite.json").read_text())
        self.assertEqual(adapter["coverage_slots"], list(BASELINE_SLOTS))
        self.assertEqual(adapter["coverage_slots"], suite["family_output_parity"]["required_slots"])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        image = Image.new("RGB", (4, 3), "#776655")
        stream = BytesIO()
        image.save(stream, format="JPEG")
        raster = pin(self.root, self.root / "source" / "field.jpg", stream.getvalue())
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="612pt" height="792pt" viewBox="0 0 612 792"><rect width="612" height="792" fill="#f4efe3"/><image href="../source/field.jpg" x="20" y="20" width="100" height="75"/></svg>'
        entry = pin(self.root, self.root / "proofs_linked" / "intro.svg", svg)
        self.manifest = {"schema_version": "0.1.0", "family_id": "sample-family", "source_state": "proposed-unselected",
                         "outputs": [{"id": "route-a", "route": "spacious", "slot": None, "context": "light",
                                      "page_pt": [612, 792], "entry": entry, "dependencies": [raster]}]}
        self.manifest_path = self.root / "manifest.json"
        self.write()

    def tearDown(self):
        self.temp.cleanup()

    def write(self):
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_unselected_route_cannot_claim_baseline_and_stale_link_rejects(self):
        self.assertEqual(len(validate_manifest(self.manifest_path)["outputs"]), 1)
        self.manifest["outputs"][0]["slot"] = "document-one-page"
        self.write()
        with self.assertRaisesRegex(NativeVectorError, "cannot claim baseline"):
            validate_manifest(self.manifest_path)
        self.manifest["outputs"][0]["slot"] = None
        self.manifest["outputs"][0]["dependencies"] = []
        self.write()
        with self.assertRaisesRegex(NativeVectorError, "resource links differ"):
            validate_manifest(self.manifest_path)
        self.manifest["outputs"][0]["dependencies"] = [{"path": "source/field.jpg", "sha256": "0" * 64}]
        self.write()
        with self.assertRaisesRegex(NativeVectorError, "bytes differ"):
            validate_manifest(self.manifest_path)

    @unittest.skipUnless(shutil.which("rsvg-convert"), "librsvg is needed for native proof integration")
    def test_build_preserves_linked_jpeg_and_exact_letter_page(self):
        result = build(self.manifest_path, self.root / "output")
        self.assertEqual(result["source_state"], "proposed-unselected")
        self.assertEqual(result["outputs"][0]["status"], "built-awaiting-visual-review")
        self.assertEqual(result["representation_check"]["raster_source_count"], 1)
        pdf = self.root / "output/pdf/route-a.pdf"
        pages = PdfReader(str(pdf)).pages
        self.assertEqual(len(pages), 1)
        self.assertAlmostEqual(float(pages[0].mediabox.width), 612, delta=.5)
        self.assertEqual(PdfReader(str(pdf)).trailer["/Root"]["/OutputIntents"][0]["/S"], "/GTS_PDFA1")
        self.assertEqual((self.root / "output/source/source/field.jpg").read_bytes(),
                         (self.root / "source/field.jpg").read_bytes())
        with Image.open(self.root / "output/previews/route-a.png") as preview:
            r, g, b, *_ = preview.convert("RGBA").getpixel((100, 100))
            self.assertTrue(90 <= r <= 150 and 70 <= g <= 130 and 60 <= b <= 120,
                            "the linked raster must visibly survive rendering")


if __name__ == "__main__":
    unittest.main()
