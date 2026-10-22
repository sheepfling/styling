"""One family may contain distinct route packets without losing their evidence boundaries."""
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
from pypdf import PdfWriter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sheepfling_styling.family_coverage import BASELINE_SLOTS, coverage_from_outputs
from sheepfling_styling.family_system import FamilySystemError, audit_family_system
from sheepfling_styling.native_vector import build as build_native_vector
from sheepfling_styling.visual_representations import validate_visual_representations


def pinned(root: Path, name: str, raw: bytes) -> dict[str, str]:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {"path": name, "sha256": hashlib.sha256(raw).hexdigest()}


def recipe_packet(root: Path, name: str, output_id: str, slot: str, context: str) -> dict[str, str]:
    packet = root / name
    source = pinned(packet, "source/main.tex", b"% Synthetic family-owned layout\n")
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buffer = BytesIO()
    writer.write(buffer)
    pdf = pinned(packet, f"pdf/{output_id}.pdf", buffer.getvalue())
    image = Image.new("RGB", (4, 4), "#b7d8ef")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    preview = pinned(packet, f"previews/{output_id}-1.png", buffer.getvalue())
    metadata = {"interface_id": "visual-asset-representations", "interface_version": "0.1.0",
                "schema_version": 1, "representations": [{"id": output_id, "representation": "derived-export",
                "path": pdf["path"], "sha256": pdf["sha256"], "source_paths": [source["path"]],
                "generator": "synthetic recipe", "rendering": "native typesetting", "format": "PDF",
                "page_count": 1, "page_map": [{"page": 1, "source_paths": [source["path"]]}]}]}
    raw = json.dumps(metadata).encode()
    pinned(packet, "representations.json", raw)
    check = validate_visual_representations(raw, {source["path"]: (packet / source["path"]).read_bytes(),
                                                  pdf["path"]: (packet / pdf["path"]).read_bytes()})
    coverage = coverage_from_outputs([{"id": output_id, "slot": slot, "context": context}])
    report = {"schema_version": 1, "family_id": "sample-packet", "status": "checks-passed-awaiting-visual-review",
              "visual_review": "pending", "pdfs": {output_id: {"path": pdf["path"], "sha256": pdf["sha256"],
              "slot": slot, "context": context, "visual_review": "pending", "checks": {"page_count": 1}}},
              "previews": {output_id: [preview]}, "coverage": coverage, "web": {"status": "not-run"},
              "representation_checks": check}
    pinned(packet, "build-report.json", json.dumps(report).encode())
    return {"path": f"{name}/build-report.json",
            "sha256": hashlib.sha256((packet / "build-report.json").read_bytes()).hexdigest()}


class FamilySystemTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.first = recipe_packet(self.root, "document-packet", "one-page", "document-one-page", "light")
        self.second = recipe_packet(self.root, "product-packet", "one-page", "product-slick", "mixed")
        self.manifest = {"schema_version": "0.1.0", "family_id": "sample-system",
                         "routes": [
                             {"id": "editorial", "state": "selected-for-now", "signature_features": [
                                 {"id": "open-rhythm", "description": "Generous family-owned spacing", "outputs": ["one-page"]}]},
                             {"id": "product", "state": "selected-for-now", "signature_features": [
                                 {"id": "image-stage", "description": "A distinct visual stage", "outputs": ["one-page"]}]}],
                         "builds": [
                             {"kind": "composition-recipe", "route": "editorial", "source_family_id": "sample-packet", "report": self.first},
                             {"kind": "composition-recipe", "route": "product", "source_family_id": "sample-packet", "report": self.second}]}
        self.path = self.root / "family-system.json"
        self.write()

    def tearDown(self):
        self.temporary.cleanup()

    def write(self):
        self.path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_route_aware_assembly_preserves_mixed_experiment(self):
        contract = json.loads((ROOT / "contracts/family-system-assembly.json").read_text())
        self.assertEqual(contract["build_kinds"], ["native-tex", "native-vector", "composition-recipe"])
        self.assertEqual(len(BASELINE_SLOTS), 5)
        report = audit_family_system(self.path)
        self.assertEqual({item["key"] for item in report["outputs"]}, {"editorial/one-page", "product/one-page"})
        self.assertEqual(report["coverage"]["document-one-page"]["outputs"], ["editorial/one-page"])
        self.assertEqual(report["coverage"]["product-slick"]["status"], "not-run")
        self.assertEqual(report["review_checklist"]["product/one-page"], ["image-stage"])
        self.assertEqual(report["review"], "pending")

    def test_changed_pdf_and_unselected_baseline_cannot_pass(self):
        path = self.root / "document-packet/pdf/one-page.pdf"
        path.write_bytes(path.read_bytes() + b"changed")
        with self.assertRaisesRegex(FamilySystemError, "bytes differ"):
            audit_family_system(self.path)
        path.write_bytes(path.read_bytes()[:-7])
        self.manifest["routes"][0]["state"] = "proposed-unselected"
        self.write()
        with self.assertRaisesRegex(FamilySystemError, "Unselected route"):
            audit_family_system(self.path)

    def test_signature_features_and_explicit_package_mapping_are_required(self):
        self.manifest["routes"][1]["signature_features"][0]["outputs"] = ["missing"]
        self.write()
        with self.assertRaisesRegex(FamilySystemError, "absent from its route"):
            audit_family_system(self.path)
        self.manifest["routes"][1]["signature_features"][0]["outputs"] = ["one-page"]
        self.manifest["builds"][1]["source_family_id"] = "another-family"
        self.write()
        with self.assertRaisesRegex(FamilySystemError, "explicit source family ID"):
            audit_family_system(self.path)


class NativeFamilyAssemblyTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("rsvg-convert"), "librsvg is needed for native assembly integration")
    def test_unselected_svg_route_keeps_exact_source_and_no_baseline_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            svg = pinned(root, "proofs/label.svg", b'<svg xmlns="http://www.w3.org/2000/svg" width="612pt" height="792pt"><rect width="612" height="792" fill="#f4e8cc"/></svg>')
            native = {"schema_version": "0.1.0", "family_id": "sample-vector",
                      "source_state": "proposed-unselected", "outputs": [
                          {"id": "label", "route": "quiet-serif", "slot": None, "context": "light",
                           "page_pt": [612, 792], "entry": svg, "dependencies": []}]}
            native_path = root / "native.json"
            native_path.write_text(json.dumps(native))
            build_native_vector(native_path, root / "native-build")
            report = pinned(root, "native-build/build-report.json", (root / "native-build/build-report.json").read_bytes())
            assembly = {"schema_version": "0.1.0", "family_id": "sample-system",
                        "routes": [{"id": "quiet-serif", "state": "proposed-unselected",
                                    "signature_features": [{"id": "paper-field", "description": "Warm paper field",
                                                            "outputs": ["label"]}]}],
                        "builds": [{"kind": "native-vector", "route": None,
                                    "source_family_id": "sample-vector", "report": report}]}
            path = root / "family-system.json"
            path.write_text(json.dumps(assembly))
            audit = audit_family_system(path)
            self.assertEqual(audit["coverage"]["document-one-page"]["status"], "not-run")
            self.assertEqual(audit["routes"][0]["outputs"], ["quiet-serif/label"])
            (root / "native-build/source/proofs/label.svg").write_bytes(b"changed")
            with self.assertRaisesRegex(FamilySystemError, "bytes differ"):
                audit_family_system(path)


if __name__ == "__main__":
    unittest.main()
