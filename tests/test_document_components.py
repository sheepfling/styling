"""Long-form feature evidence must be page-specific and tied to current PDF bytes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from pypdf import PdfWriter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sheepfling_styling.document_components import (
    FEATURE_IDS, ComponentProofError, audit_document_component_proof, validate_feature_evidence,
)


def plan() -> dict:
    return {"schema_version": "0.1.0", "family_id": "sample-family", "output_id": "atlas",
            "features": {feature: {"status": "not-run", "pages": [], "anchors": [], "note": "Not in this bounded proof."}
                         for feature in FEATURE_IDS}}


class DocumentComponentTests(unittest.TestCase):
    def test_contract_and_page_specific_internal_link_evidence(self):
        contract = json.loads((ROOT / "contracts/document-component-proof.json").read_text())
        self.assertEqual(tuple(contract["feature_ids"]), FEATURE_IDS)
        value = plan()
        value["features"]["title-page"] = {"status": "exercised", "pages": [1],
                                            "anchors": ["Working specimen"], "note": "Visible title-page status."}
        value["features"]["table-of-contents"] = {"status": "exercised", "pages": [1],
                                                     "anchors": ["Generated contents"], "min_internal_links": 2,
                                                     "note": "Linked final page references."}
        result = validate_feature_evidence(value, ["Working specimen. Generated contents.", "Other page."], [2, 0])
        self.assertEqual(result["exercised_count"], 2)
        self.assertEqual(result["features"]["table-of-contents"]["internal_links"], 2)

    def test_missing_anchor_or_links_cannot_claim_component(self):
        value = plan()
        value["features"]["table-of-contents"] = {"status": "exercised", "pages": [1],
                                                     "anchors": ["Generated contents"], "min_internal_links": 2,
                                                     "note": "Linked final page references."}
        with self.assertRaisesRegex(ComponentProofError, "text anchor"):
            validate_feature_evidence(value, ["Wrong text"], [2])
        with self.assertRaisesRegex(ComponentProofError, "too few internal"):
            validate_feature_evidence(value, ["Generated contents"], [1])
        value["features"]["figures"]["anchors"] = ["Figure 1"]
        with self.assertRaisesRegex(ComponentProofError, "not-run evidence"):
            validate_feature_evidence(value, ["Generated contents"], [2])

    def test_changed_pdf_invalidates_feature_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            writer = PdfWriter()
            writer.add_blank_page(width=612, height=792)
            pdf = root / "atlas.pdf"
            with pdf.open("wb") as stream:
                writer.write(stream)
            report = {"family_id": "sample-family", "pdfs": {"atlas": {
                "slot": "component-proof", "context": "light", "path": "atlas.pdf",
                "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(), "checks": {"pages": 1}}}}
            report_path, plan_path = root / "build-report.json", root / "feature-plan.json"
            report_path.write_text(json.dumps(report))
            plan_path.write_text(json.dumps(plan()))
            self.assertEqual(audit_document_component_proof(plan_path, report_path)["not_run_count"], len(FEATURE_IDS))
            pdf.write_bytes(pdf.read_bytes() + b"changed")
            with self.assertRaisesRegex(ComponentProofError, "hash is stale"):
                audit_document_component_proof(plan_path, report_path)


if __name__ == "__main__":
    unittest.main()
