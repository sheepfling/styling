"""The shared typesetting contract keeps output slots common and accents local."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts/typography-deliverable-suite.json"
CONTENT_SCHEMA = ROOT / "contracts/typography-content-manifest.json"


class TypographyDeliverableContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_all_families_share_the_same_light_output_slots(self):
        self.assertEqual(self.contract["suite_id"], "shared-typography-deliverables")
        self.assertEqual(self.contract["suite_version"], "0.5.0")
        parity = self.contract["family_output_parity"]
        required = ["document-one-page", "document-two-page", "web-light", "product-slick", "component-proof"]
        self.assertEqual(parity["required_slots"], required)
        self.assertTrue(parity["all_families_have_same_slots"])
        self.assertEqual(parity["context"], "light")
        outputs = {item["id"]: item for item in self.contract["baseline_outputs"]}
        self.assertEqual(set(outputs), set(required))
        self.assertTrue(all(outputs[slot]["context"] == "light" for slot in required))
        self.assertEqual(outputs["component-proof"]["page_count"], 6)
        role_policy = self.contract["typography_role_policy"]
        self.assertTrue(role_policy["all_families_map_the_same_semantic_roles"])
        self.assertEqual(role_policy["physical_face_ids"], ["body", "display", "strong", "wordmark", "mono"])
        families = {item["id"] for item in self.contract["profile_slots"]}
        self.assertEqual(families, {"system-01", "system-02", "system-03", "system-04", "system-05", "system-06"})

    def test_accents_and_long_form_components_remain_profile_owned(self):
        accents = {item["id"] for item in self.contract["profile_owned_accent_slots"]}
        self.assertTrue({"section-marker", "divider", "informative-panel", "data-encoding", "identity-accent", "wayfinding"}.issubset(accents))
        components = {item["id"] for item in self.contract["long_form_document_components"]["components"]}
        self.assertTrue({"title-page", "heading-hierarchy", "narrative-body", "figures", "tables", "references", "appendix", "footnotes", "running-matter", "informative-cards"}.issubset(components))

    def test_content_schema_declares_one_page_and_product_slick_blocks(self):
        schema = json.loads(CONTENT_SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(self.contract["content_manifest_schema"], "contracts/typography-content-manifest.json")
        self.assertIn("one_page", schema["required_blocks"])
        self.assertIn("product_slick", schema["required_blocks"])
        self.assertIn("summary", schema["one_page"]["required_fields"])
        self.assertGreaterEqual(schema["product_slick"]["minimum_highlights"], 2)
        self.assertGreaterEqual(schema["product_slick"]["minimum_facts"], 2)
        self.assertIn("source_records", schema)


if __name__ == "__main__":
    unittest.main()
