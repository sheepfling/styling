"""The bounded sample output remains a single-page sRGB PDF proof."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "examples/starter/output"


class PreviewExportTests(unittest.TestCase):
    def test_generated_pdf_has_one_page_and_srgb_output_intent(self):
        reader = PdfReader(str(OUTPUT / "preview.pdf"))
        self.assertEqual(len(reader.pages), 1)
        intents = reader.trailer["/Root"].get("/OutputIntents")
        self.assertTrue(intents)
        self.assertEqual(intents[0].get("/OutputConditionIdentifier"), "sRGB IEC61966-2.1")
        output_profile = intents[0]["/DestOutputProfile"].get_object()
        self.assertEqual(output_profile["/N"], 3)
        self.assertGreater(len(output_profile.get_data()), 128)
        self.assertIn("starter-mark", (OUTPUT / "preview.svg").read_text(encoding="utf-8"))
        representations = json.loads((OUTPUT / "representations.json").read_text(encoding="utf-8"))
        self.assertEqual(representations["representations"][1]["page_count"], 1)
        index = json.loads((OUTPUT / "output-index.json").read_text(encoding="utf-8"))
        self.assertEqual(index["outputs"][0]["status"], "current_proof")


if __name__ == "__main__":
    unittest.main()
