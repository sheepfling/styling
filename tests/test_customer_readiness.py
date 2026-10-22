"""Customer evidence advances only when exact sources and reviews are present."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sheepfling_styling.customer_intake import IntakeError, load_and_validate_intake, validate_intake
from sheepfling_styling.portfolio_coverage import CoverageError, build_portfolio_report

SAMPLE = ROOT / "examples/starter/customer-intake.json"


def pin(root: Path, name: str, data: bytes) -> dict[str, str]:
    (root / name).write_bytes(data)
    return {"path": name, "sha256": hashlib.sha256(data).hexdigest()}


def png_image(width: int = 1, height: int = 1) -> bytes:
    def chunk(name: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress((b"\x00" + b"\x00\x00\x00\x00" * width) * height))
            + chunk(b"IEND", b""))


class CustomerIntakeTests(unittest.TestCase):
    def test_synthetic_intake_checks_real_source_and_rights_bytes(self):
        summary = load_and_validate_intake(SAMPLE)
        self.assertEqual(summary["profile_id"], "system-01")
        self.assertEqual(summary["source_count"], 1)
        self.assertFalse(summary["profile_ready"])
        self.assertEqual(summary["publication"], "not-cleared")

    def test_unproved_rights_and_invalid_state_transitions_reject(self):
        original = json.loads(SAMPLE.read_text(encoding="utf-8"))
        data = copy.deepcopy(original)
        data["sources"][0]["rights"]["evidence"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(IntakeError, "bytes differ"):
            validate_intake(data, SAMPLE.parent)
        data = copy.deepcopy(original)
        data["states"]["production"] = "approved"
        with self.assertRaises(IntakeError):
            validate_intake(data, SAMPLE.parent)
        data = copy.deepcopy(original)
        data["sources"][0]["rights"]["status"] = "pending"
        with self.assertRaises(IntakeError):
            validate_intake(data, SAMPLE.parent)
        data = copy.deepcopy(original)
        data["typefaces"] = {"status": "selected", "bindings": {"body": "starter-mark", "display": "starter-mark", "strong": "starter-mark"}}
        with self.assertRaisesRegex(IntakeError, "font source"):
            validate_intake(data, SAMPLE.parent)
        data = copy.deepcopy(original)
        data["route"]["status"] = ["approved"]
        with self.assertRaises(IntakeError):
            validate_intake(data, SAMPLE.parent)


class PortfolioCoverageTests(unittest.TestCase):
    def test_default_report_exposes_all_thirty_gaps(self):
        report = build_portfolio_report(ROOT)
        self.assertEqual(report["profile_count"], 6)
        self.assertEqual(report["slot_count"], 30)
        self.assertEqual(report["status_counts"]["not-started"], 30)
        self.assertEqual(report["summary"]["reviewed_or_approved_slots"], 0)
        self.assertEqual(len(report["profiles"][0]["slots"]), 5)

    def test_reviewed_pdf_requires_current_artifact_and_receipt_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            from pypdf import PdfReader
            pdf_bytes = (ROOT / "examples/starter/output/preview.pdf").read_bytes()
            artifact = pin(root, "slick.pdf", pdf_bytes)
            reader = PdfReader(str(root / "slick.pdf"))
            preview = pin(root, "page-1.png", png_image())
            character = {"reference": pin(root, "family-brief.txt", b"Synthetic signature: spacious reading rhythm"),
                         "features": [{"name": "reading rhythm", "disposition": "preserved",
                                       "evidence": "Review at actual page size confirms the intended open rhythm."}]}
            review = {"schema_version": "0.1.0", "status": "passed", "reviewer": "Fixture reviewer",
                      "reviewed_at": "2026-10-21", "intended_use": "Synthetic screen proof at actual page size",
                      "artifact": artifact,
                      "pages": [{"number": index, "size_pt": [float(page.mediabox.width), float(page.mediabox.height)],
                                 "preview": preview, "findings": []}
                                for index, page in enumerate(reader.pages, start=1)],
                      "family_character": character,
                      "blocking_findings": [], "limitations": []}
            record = {"schema_version": "0.1.0", "profile_id": "system-01", "slots": {
                "product-slick": {"status": "reviewed", "context": "light",
                                  "input": pin(root, "source.json", b"source"),
                                  "output": artifact,
                                  "review": pin(root, "review.json", json.dumps(review).encode()),
                                  "browser": None, "approval": None, "print": None, "reason": None}}}
            (root / "system-01.json").write_text(json.dumps(record), encoding="utf-8")
            report = build_portfolio_report(ROOT, evidence_dir=root)
            self.assertEqual(report["status_counts"]["reviewed"], 1)
            self.assertEqual(report["status_counts"]["not-started"], 29)
            self.assertIsNotNone(report["profiles"][0]["slots"]["product-slick"]["review_sha256"])
            changed_review = copy.deepcopy(review)
            changed_review["family_character"]["features"][0]["disposition"] = "missing"
            record["slots"]["product-slick"]["review"] = pin(root, "review-missing.json", json.dumps(changed_review).encode())
            (root / "system-01.json").write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(CoverageError, "signature feature missing"):
                build_portfolio_report(ROOT, evidence_dir=root)
            record["slots"]["product-slick"]["review"] = pin(root, "review.json", json.dumps(review).encode())
            record["slots"]["product-slick"]["status"] = "approved"
            record["slots"]["product-slick"]["approval"] = pin(root, "approval.json", b"synthetic approval")
            (root / "system-01.json").write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(CoverageError, "profile-ready intake"):
                build_portfolio_report(ROOT, evidence_dir=root)
            record["slots"]["product-slick"]["status"] = "reviewed"
            record["slots"]["product-slick"]["approval"] = None
            (root / "system-01.json").write_text(json.dumps(record), encoding="utf-8")
            (root / "slick.pdf").write_bytes(b"changed")
            with self.assertRaisesRegex(CoverageError, "bytes differ"):
                build_portfolio_report(ROOT, evidence_dir=root)

    def test_web_review_and_baseline_context_cannot_be_inferred(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = pin(root, "index.html", b"<html><head><link rel='stylesheet' href='style.css'></head><body></body></html>")
            checks = {name: "passed" for name in ("reflow", "images", "computed_fonts", "keyboard_focus", "reduced_motion", "links", "contrast")}
            browser = {"schema_version": "0.1.0", "status": "passed", "reviewer": "Fixture reviewer",
                       "reviewed_at": "2026-10-21", "intended_use": "Synthetic web proof",
                       "browser": {"name": "Chromium", "version": "fixture"}, "entry": entry,
                       "sources": [pin(root, "style.css", b"body { color: black; }")],
                       "viewports": [{"width": width, "height": 600,
                                      "screenshot": pin(root, f"width-{width}.png", png_image(width, 600)),
                                      "checks": checks} for width in (320, 390, 768, 1280)],
                       "family_character": {"reference": pin(root, "family-web-brief.txt", b"Synthetic web rhythm"),
                                            "features": [{"name": "rhythm", "disposition": "adapted",
                                                          "evidence": "Spacing intentionally reflows at narrow widths."}]},
                       "blocking_findings": [], "limitations": []}
            slot = {"status": "reviewed", "context": "light",
                    "input": pin(root, "web-source.json", b"source"),
                    "output": entry,
                    "review": None, "browser": None, "approval": None, "print": None, "reason": None}
            record = {"schema_version": "0.1.0", "profile_id": "system-01", "slots": {"web-light": slot}}
            (root / "system-01.json").write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaises(CoverageError):
                build_portfolio_report(ROOT, evidence_dir=root)
            slot["browser"] = pin(root, "browser.json", json.dumps(browser).encode())
            (root / "system-01.json").write_text(json.dumps(record), encoding="utf-8")
            self.assertEqual(build_portfolio_report(ROOT, evidence_dir=root)["status_counts"]["reviewed"], 1)
            (root / "width-390.png").write_bytes(b"changed")
            with self.assertRaisesRegex(CoverageError, "bytes differ"):
                build_portfolio_report(ROOT, evidence_dir=root)
            (root / "width-390.png").write_bytes(png_image(390, 600))
            slot["context"] = "dark"
            (root / "system-01.json").write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(CoverageError, "non-light"):
                build_portfolio_report(ROOT, evidence_dir=root)


if __name__ == "__main__":
    unittest.main()
