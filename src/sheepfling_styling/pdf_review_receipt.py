"""Validate exact-byte PDF screen-review receipts and complete page coverage."""
from __future__ import annotations

from datetime import date
import math
from pathlib import Path
from typing import Any

from .customer_intake import IntakeError, pinned_file, read_intake
from .family_character import FamilyCharacterError, validate_family_character


class ReviewError(ValueError):
    """A PDF visual-review receipt is incomplete, stale, or contradictory."""


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 2048:
        raise ReviewError(f"{label} must be non-empty text")
    return value


def _strings(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ReviewError(f"{label} must be a list")
    for item in value:
        _text(item, label)
    return value


def validate_pdf_review_receipt(receipt_path: Path, expected_pdf_sha256: str | None = None) -> dict[str, Any]:
    try:
        data = read_intake(receipt_path)
    except IntakeError as exc:
        raise ReviewError(str(exc)) from exc
    fields = {"schema_version", "status", "reviewer", "reviewed_at", "intended_use", "artifact", "pages", "family_character", "blocking_findings", "limitations"}
    if set(data) != fields or data["schema_version"] != "0.1.0" or not isinstance(data["status"], str) or data["status"] not in {"passed", "blocked"}:
        raise ReviewError("Unsupported PDF visual-review receipt structure or status")
    _text(data["reviewer"], "reviewer")
    _text(data["intended_use"], "intended_use")
    try:
        date.fromisoformat(data["reviewed_at"])
    except (TypeError, ValueError) as exc:
        raise ReviewError("reviewed_at must be an ISO date") from exc
    _strings(data["blocking_findings"], "blocking_findings")
    _strings(data["limitations"], "limitations")
    if data["status"] == "passed" and data["blocking_findings"]:
        raise ReviewError("Passed review may not have blocking findings")
    try:
        character = validate_family_character(data["family_character"], receipt_path.parent, data["status"] == "passed")
    except FamilyCharacterError as exc:
        raise ReviewError(str(exc)) from exc
    try:
        pdf = pinned_file(receipt_path.parent, data["artifact"], "artifact")
    except IntakeError as exc:
        raise ReviewError(str(exc)) from exc
    if pdf.suffix.lower() != ".pdf":
        raise ReviewError("Review artifact must be a PDF")
    if expected_pdf_sha256 is not None and data["artifact"]["sha256"] != expected_pdf_sha256:
        raise ReviewError("Review artifact hash does not match the coverage output")
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:
        raise ReviewError("pypdf is required to verify page coverage") from exc
    try:
        reader = PdfReader(str(pdf))
    except (OSError, ValueError, PdfReadError) as exc:
        raise ReviewError("A readable PDF and pypdf are required to verify page coverage") from exc
    pages = data["pages"]
    if not isinstance(pages, list) or len(pages) != len(reader.pages):
        raise ReviewError("Review page records must cover every PDF page")
    for index, (record, page) in enumerate(zip(pages, reader.pages), start=1):
        if not isinstance(record, dict) or set(record) != {"number", "size_pt", "preview", "findings"} or type(record["number"]) is not int or record["number"] != index:
            raise ReviewError("Review page numbers must cover the PDF in order")
        size = record["size_pt"]
        if not isinstance(size, list) or len(size) != 2 or any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0 for value in size):
            raise ReviewError(f"Page {index} needs a positive point-size pair")
        actual = [float(page.mediabox.width), float(page.mediabox.height)]
        if any(abs(float(size[i]) - actual[i]) > 0.5 for i in (0, 1)):
            raise ReviewError(f"Page {index} size differs from the reviewed PDF")
        try:
            preview = pinned_file(receipt_path.parent, record["preview"], f"page {index} preview")
        except IntakeError as exc:
            raise ReviewError(str(exc)) from exc
        try:
            from PIL import Image
            with Image.open(preview) as image:
                if image.format != "PNG":
                    raise ReviewError(f"Page {index} preview must be a PNG")
                image.verify()
        except (ImportError, OSError, ValueError) as exc:
            raise ReviewError(f"Page {index} needs a readable PNG preview and Pillow") from exc
        _strings(record["findings"], f"page {index} findings")
    return {"status": data["status"], "reviewer": data["reviewer"],
            "reviewed_at": data["reviewed_at"], "page_count": len(pages),
            "artifact_sha256": data["artifact"]["sha256"],
            "blocking_findings": len(data["blocking_findings"]),
            "family_character": character,
            "limitation_count": len(data["limitations"])}
