"""The public registry keeps six system profiles isolated and inactive."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ProfileRegistryTests(unittest.TestCase):
    def test_six_slots_are_distinct_and_wait_for_source_review(self):
        registry = json.loads((ROOT / "profiles/registry.json").read_text(encoding="utf-8"))
        profiles = registry["profiles"]
        self.assertEqual(len(profiles), 6)
        self.assertEqual(len({item["profile_id"] for item in profiles}), 6)
        self.assertEqual(len({item["path"] for item in profiles}), 6)
        for item in profiles:
            profile = json.loads((ROOT / item["path"]).read_text(encoding="utf-8"))
            self.assertEqual(profile["profile_id"], item["profile_id"])
            self.assertEqual(profile["status"], "source-review-pending")
            self.assertIsNone(profile["asset_pack_id"])
            self.assertEqual(profile["output_capabilities"], [])


if __name__ == "__main__":
    unittest.main()
