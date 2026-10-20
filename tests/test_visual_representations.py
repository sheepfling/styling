"""Order-independent representation and output-index validation checks."""
from __future__ import annotations

import hashlib
import json
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sheepfling_styling.visual_representations import (  # noqa: E402
    RepresentationError,
    validate_output_index,
    validate_representation_contract,
    validate_visual_representations,
)


def png_rgba(width: int, height: int) -> bytes:
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + header + b"\x00\x00\x00\x00"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class VisualRepresentationTests(unittest.TestCase):
    def setUp(self):
        raster = png_rgba(1536, 1024)
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><image href="../assets/sample-mark.png"/></svg>'
        pdf = b"%PDF-1.4\nproof\n"
        self.files = {
            "assets/sample-mark.png": raster,
            "generated/screen.svg": svg,
            "proofs/output.pdf": pdf,
        }
        # Put the vector entry first to ensure metadata order does not affect linked-source resolution.
        self.representations = {
            "interface_id": "visual-asset-representations",
            "interface_version": "0.1.0",
            "schema_version": 1,
            "representations": [
                {
                    "id": "screen",
                    "representation": "vector-master",
                    "path": "generated/screen.svg",
                    "sha256": digest(svg),
                    "linked_raster_sources": ["sample-mark"],
                    "editable": True,
                },
                {
                    "id": "sample-mark",
                    "representation": "raster-source",
                    "path": "assets/sample-mark.png",
                    "sha256": digest(raster),
                    "width": 1536,
                    "height": 1024,
                    "color_mode": "RGBA",
                    "master_status": "no-vector-master",
                },
                {
                    "id": "proofbook",
                    "representation": "derived-export",
                    "path": "proofs/output.pdf",
                    "sha256": digest(pdf),
                    "source_paths": ["generated/screen.svg"],
                    "generator": "test fixture",
                    "rendering": "static visual export",
                    "format": "PDF",
                    "page_count": 1,
                    "page_map": [{"page": 1, "source_paths": ["generated/screen.svg"]}],
                },
            ],
        }

    def test_representation_contract_and_index_validate_when_raster_is_listed_after_vector(self):
        contract = (ROOT / "contracts/visual-asset-representations.json").read_bytes()
        self.assertEqual(validate_representation_contract(contract)["status"], "passed")
        check = validate_visual_representations(json.dumps(self.representations).encode(), self.files)
        self.assertEqual(check["vector_master_count"], 1)
        self.assertEqual(check["raster_source_count"], 1)

        index = {
            "schema_version": 1,
            "proof_pdf_path": "proofs/output.pdf",
            "proof_sha256": digest(self.files["proofs/output.pdf"]),
            "page_count": 1,
            "outputs": [{
                "output_id": "screen_proof",
                "status": "current_proof",
                "page": 1,
                "source_paths": ["generated/screen.svg"],
            }],
        }
        self.assertEqual(validate_output_index(json.dumps(index).encode(), self.files)["status"], "passed")
        index["proof_sha256"] = "0" * 64
        with self.assertRaisesRegex(RepresentationError, "digest"):
            validate_output_index(json.dumps(index).encode(), self.files)


if __name__ == "__main__":
    unittest.main()
