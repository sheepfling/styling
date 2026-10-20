"""Checks for exact asset-pack selection, hashes and repository boundaries."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sheepfling_styling.asset_pack_contract import AssetPackError, load_asset_pack  # noqa: E402


class AssetPackContractTests(unittest.TestCase):
    def test_exact_starter_pack_resolves_the_pinned_local_vector(self):
        pack = load_asset_pack(ROOT, "contracts/asset-packs.json", "starter-sample-assets")
        self.assertEqual(pack["availability"], "local_assets_present")
        self.assertEqual(len(pack["assets"]), 1)
        self.assertTrue(pack["assets"][0]["resolved_local"])

    def test_unknown_pack_is_not_guessed(self):
        with self.assertRaisesRegex(AssetPackError, "exactly one record"):
            load_asset_pack(ROOT, "contracts/asset-packs.json", "another-pack")

    def test_traversal_in_contract_source_path_is_rejected(self):
        contract_path = ROOT / "contracts/asset-packs.json"
        data = json.loads(contract_path.read_text(encoding="utf-8"))
        data["packs"][0]["assets"][0]["path"] = "../../outside.svg"
        temporary = ROOT / "contracts/invalid-test-contract.json"
        try:
            temporary.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(AssetPackError):
                load_asset_pack(ROOT, temporary, "starter-sample-assets")
        finally:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
