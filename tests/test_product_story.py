"""Product semantics and image stages are checked without prescribing typography."""
from __future__ import annotations

from io import BytesIO
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sheepfling_styling.family_coverage import coverage_from_outputs
from sheepfling_styling.product_story import ProductStoryError, audit_product_story
from sheepfling_styling.visual_representations import validate_visual_representations


def pin(root: Path, name: str, raw: bytes) -> dict[str, str]:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {"path": name, "sha256": hashlib.sha256(raw).hexdigest()}


def pdf_with_text(text: str) -> bytes:
    writer = PdfWriter()
    for number in (1, 2):
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                 NameObject("/Subtype"): NameObject("/Type1"),
                                 NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        message = text if number == 1 else "BACK"
        stream = DecodedStreamObject()
        stream.set_data(("BT /F1 12 Tf 20 700 Td (" + message + ") Tj ET").encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


class ProductStoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        packet = self.root / "product-build"
        source = pin(packet, "source/main.tex", b"% family-owned native page\n")
        content = {"identity_name": "ORBIT", "identity_backronym": "Operational Research Base for Interplanetary Transit",
                   "identity_descriptor": "RESEARCH VIEW", "identity_suite_index": "01",
                   "media_hero_caption": "SAMPLE VIEW", "media_hero_status": "SYNTHETIC SAMPLE",
                   "front_lead": "A synthetic fictional scene"}
        content_pin = pin(packet, "editable-source/product/content.json", json.dumps(content).encode())
        image = Image.new("RGB", (6, 4), "#51867b")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        asset = pin(packet, "editable-source/product/assets/hero.png", buffer.getvalue())
        pdf = pin(packet, "pdf/product.pdf", pdf_with_text("ORBIT Operational Research Base for Interplanetary Transit RESEARCH VIEW SYNTHETIC SAMPLE SAMPLE VIEW"))
        self.assertIn("ORBIT", PdfReader(str(packet / pdf["path"])).pages[0].extract_text())
        previews = []
        for number in (1, 2):
            buffer = BytesIO()
            Image.new("RGB", (4, 4), "#e5ebe2").save(buffer, format="PNG")
            previews.append(pin(packet, f"previews/product-{number}.png", buffer.getvalue()))
        metadata = {"interface_id": "visual-asset-representations", "interface_version": "0.1.0",
                    "schema_version": 1, "representations": [
                        {"id": "hero", "representation": "raster-source", "path": asset["path"],
                         "sha256": asset["sha256"], "width": 6, "height": 4, "color_mode": "RGB",
                         "master_status": "no-vector-master"},
                        {"id": "product", "representation": "derived-export", "path": pdf["path"],
                         "sha256": pdf["sha256"], "source_paths": [source["path"], content_pin["path"], asset["path"]],
                         "generator": "synthetic native recipe", "rendering": "family composition", "format": "PDF",
                         "page_count": 2, "page_map": [{"page": number, "source_paths": [source["path"], content_pin["path"], asset["path"]]}
                                                       for number in (1, 2)]}]}
        raw = json.dumps(metadata).encode()
        pin(packet, "representations.json", raw)
        files = {item["path"]: (packet / item["path"]).read_bytes() for item in (source, content_pin, asset, pdf)}
        check = validate_visual_representations(raw, files)
        duplex = {"schema_version": "0.1.0", "flip": "long-edge", "front_page": 1, "back_page": 2,
                  "sheet_count": 1, "page_faces": [{"page": 1, "sheet": 1, "face": "front"},
                                                   {"page": 2, "sheet": 1, "face": "back"}],
                  "imposition": "none", "physical_print_review": "pending"}
        report = {"family_id": "sample-products", "status": "checks-passed-awaiting-visual-review",
                  "visual_review": "pending", "pdfs": {"product": {"path": pdf["path"], "sha256": pdf["sha256"],
                  "slot": "product-slick", "context": "mixed", "visual_review": "pending",
                  "checks": {"page_count": 2}, "duplex": duplex,
                  "source_hashes": {content_pin["path"]: content_pin["sha256"]}}},
                  "previews": {"product": previews},
                  "coverage": coverage_from_outputs([{"id": "product", "slot": "product-slick", "context": "mixed"}]),
                  "web": {"status": "not-run"}, "representation_checks": check,
                  "assets": {"product": [{"path": asset["path"], "sha256": asset["sha256"],
                                          "width": 6, "height": 4}]}}
        report_pin = pin(self.root, "product-build/build-report.json", json.dumps(report).encode())
        family_manifest = {"schema_version": "0.1.0", "family_id": "sample-family",
                           "routes": [{"id": "product-route", "state": "selected-for-now",
                                       "signature_features": [{"id": "distinct-title", "description": "Native title treatment",
                                                               "outputs": ["product"]}]}],
                           "builds": [{"kind": "composition-recipe", "route": "product-route",
                                       "source_family_id": "sample-products", "report": report_pin}]}
        family_pin = pin(self.root, "family-system.json", json.dumps(family_manifest).encode())
        self.story = {"schema_version": "0.1.0", "family_system": family_pin,
                      "products": [{"id": "orbit", "proof": "product-route/product",
                                    "identity": {"name": "ORBIT", "backronym": "Operational Research Base for Interplanetary Transit",
                                                 "descriptor": "RESEARCH VIEW", "sequence": 1},
                                    "media": [{"id": "hero", "asset": asset,
                                               "status": "generated-stand-in", "status_label": "SYNTHETIC SAMPLE",
                                               "fit": "contain", "caption": "SAMPLE VIEW",
                                               "caption_field": "media_hero_caption", "status_field": "media_hero_status",
                                               "stage": {"page": 1,
                                                         "panel": {"x_mm": 14, "y_mm": 100, "width_mm": 100, "height_mm": 60},
                                                         "inset_mm": 4,
                                                         "caption_box": {"x_mm": 14, "y_mm": 165, "width_mm": 100, "height_mm": 10}}}],
                                    "facets": [{"id": "vehicle-view", "label": "Vehicle context",
                                                "evidence_field": "front_lead", "media": ["hero"]}],
                                    "links": []}]}
        self.path = self.root / "product-story.json"
        self.write()

    def tearDown(self):
        self.temp.cleanup()

    def write(self):
        self.path.write_text(json.dumps(self.story))

    def test_product_story_binds_duplex_identity_and_contained_media(self):
        audit = audit_product_story(self.path)
        self.assertEqual(audit["family_id"], "sample-family")
        self.assertEqual(audit["products"][0]["identity"]["name"], "ORBIT")
        self.assertEqual(audit["products"][0]["duplex"]["flip"], "long-edge")
        self.assertEqual(audit["products"][0]["media"][0]["contained_image_mm"], [78.0, 52.0])
        self.assertEqual(audit["review"], "pending")

    def test_caption_overlap_and_identity_drift_reject(self):
        self.story["products"][0]["media"][0]["stage"]["caption_box"]["y_mm"] = 120
        self.write()
        with self.assertRaisesRegex(ProductStoryError, "overlaps"):
            audit_product_story(self.path)
        self.story["products"][0]["media"][0]["stage"]["caption_box"]["y_mm"] = 165
        self.story["products"][0]["identity"]["backronym"] = "Bad Name"
        self.write()
        with self.assertRaisesRegex(ProductStoryError, "backronym initials"):
            audit_product_story(self.path)

    def test_changed_image_and_unresolved_link_reject(self):
        self.story["products"][0]["links"] = [{"to": "unknown", "relationship": "continues in"}]
        self.write()
        with self.assertRaisesRegex(ProductStoryError, "same suite"):
            audit_product_story(self.path)
        self.story["products"][0]["links"] = []
        self.write()
        path = self.root / "product-build/editable-source/product/assets/hero.png"
        path.write_bytes(path.read_bytes() + b"changed")
        with self.assertRaisesRegex(ProductStoryError, "Family proof audit"):
            audit_product_story(self.path)


if __name__ == "__main__":
    unittest.main()
