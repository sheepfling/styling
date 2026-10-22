"""Audit page-level evidence for a family-owned long-form PDF proof.

The audit checks exact bytes, page text and internal links. It deliberately does
not choose a layout or infer that a visual treatment is good from text matches.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any


FEATURE_IDS = (
    "title-page", "table-of-contents", "heading-hierarchy", "narrative-body",
    "figures", "tables", "references", "appendix", "footnotes",
    "running-matter", "informative-cards", "lists", "highlights-underlines",
    "equations", "accent-marks", "image-provenance",
)


class ComponentProofError(ValueError):
    """The component plan or its claimed PDF evidence is incomplete or stale."""


def _read_object(path: Path) -> dict[str, Any]:
    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ComponentProofError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ComponentProofError(f"Cannot read component proof: {path}") from exc
    if not isinstance(data, dict):
        raise ComponentProofError("Component proof JSON root must be an object")
    return data


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _normalized(value: str) -> str:
    return " ".join(value.split()).casefold()


def validate_feature_evidence(plan: dict[str, Any], page_texts: list[str], internal_links: list[int]) -> dict[str, Any]:
    """Check a closed feature plan against already extracted PDF page evidence."""
    if set(plan) != {"schema_version", "family_id", "output_id", "features"} or plan["schema_version"] != "0.1.0":
        raise ComponentProofError("Unsupported component proof plan structure")
    if any(not isinstance(plan[key], str) or not plan[key].strip() for key in ("family_id", "output_id")):
        raise ComponentProofError("Component proof needs family_id and output_id")
    features = plan["features"]
    if not isinstance(features, dict) or set(features) != set(FEATURE_IDS):
        raise ComponentProofError("Component proof must declare every feature ID exactly once")
    if not page_texts or len(page_texts) != len(internal_links):
        raise ComponentProofError("Page text and internal-link counts must cover the same nonempty PDF")
    if any(not isinstance(text, str) for text in page_texts) or any(type(count) is not int or count < 0 for count in internal_links):
        raise ComponentProofError("Invalid extracted page evidence")
    checks: dict[str, Any] = {}
    for feature_id in FEATURE_IDS:
        record = features[feature_id]
        required = {"status", "pages", "anchors", "note"}
        if not isinstance(record, dict) or not required.issubset(record) or set(record) - required - {"min_internal_links"}:
            raise ComponentProofError(f"{feature_id} has an unsupported feature record")
        status, pages, anchors, note = (record[key] for key in ("status", "pages", "anchors", "note"))
        if status not in {"exercised", "not-run"} or not isinstance(note, str) or not note.strip() or len(note) > 500:
            raise ComponentProofError(f"{feature_id} needs a valid status and note")
        if not isinstance(pages, list) or not isinstance(anchors, list):
            raise ComponentProofError(f"{feature_id} needs pages and anchors lists")
        if status == "not-run":
            if pages or anchors or "min_internal_links" in record:
                raise ComponentProofError(f"{feature_id} not-run evidence must be empty")
            checks[feature_id] = {"status": status, "pages": []}
            continue
        if not pages or any(type(page) is not int or page < 1 or page > len(page_texts) for page in pages) or pages != sorted(set(pages)):
            raise ComponentProofError(f"{feature_id} needs unique, ordered existing pages")
        if not anchors or any(not isinstance(anchor, str) or not 3 <= len(anchor.strip()) <= 240 for anchor in anchors):
            raise ComponentProofError(f"{feature_id} needs visible text anchors")
        text = _normalized(" ".join(page_texts[page - 1] for page in pages))
        for anchor in anchors:
            if _normalized(anchor) not in text:
                raise ComponentProofError(f"{feature_id} missing page-level text anchor: {anchor!r}")
        minimum = record.get("min_internal_links")
        if minimum is not None:
            if feature_id != "table-of-contents" or type(minimum) is not int or not 1 <= minimum <= 100:
                raise ComponentProofError("Only table-of-contents may require internal links")
            if sum(internal_links[page - 1] for page in pages) < minimum:
                raise ComponentProofError("Table of contents has too few internal PDF links")
        checks[feature_id] = {"status": status, "pages": pages, "anchors": len(anchors),
                              "internal_links": sum(internal_links[page - 1] for page in pages)}
    exercised = sum(record["status"] == "exercised" for record in checks.values())
    return {"status": "checks-passed-awaiting-visual-review", "feature_count": len(FEATURE_IDS),
            "exercised_count": exercised, "not_run_count": len(FEATURE_IDS) - exercised,
            "features": checks}


def _internal_link_count(page: Any) -> int:
    count = 0
    for reference in page.get("/Annots", []):
        annotation = reference.get_object()
        if annotation.get("/Subtype") != "/Link":
            continue
        action = annotation.get("/A")
        if annotation.get("/Dest") is not None or (action and action.get("/S") == "/GoTo"):
            count += 1
    return count


def audit_document_component_proof(plan_path: Path, report_path: Path) -> dict[str, Any]:
    plan_path, report_path = plan_path.resolve(), report_path.resolve()
    plan, report = _read_object(plan_path), _read_object(report_path)
    if report.get("family_id") != plan.get("family_id"):
        raise ComponentProofError("Build report family differs from component plan")
    output = report.get("pdfs", {}).get(plan.get("output_id"))
    if not isinstance(output, dict) or output.get("slot") != "component-proof" or output.get("context") != "light":
        raise ComponentProofError("Build report lacks the light component-proof PDF")
    value = output.get("path")
    if not isinstance(value, str) or not value or PurePosixPath(value).is_absolute() or ".." in PurePosixPath(value).parts:
        raise ComponentProofError("Build report has an unsafe PDF path")
    pdf = (report_path.parent / value).resolve()
    if not pdf.is_relative_to(report_path.parent) or not pdf.is_file() or pdf.suffix.lower() != ".pdf":
        raise ComponentProofError("Build report PDF is missing or escapes its output root")
    pdf_hash = _sha256(pdf)
    if output.get("sha256") != pdf_hash:
        raise ComponentProofError("Build report PDF hash is stale")
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:
        raise ComponentProofError("pypdf is required to read component PDF evidence") from exc
    try:
        reader = PdfReader(str(pdf), strict=True)
        page_texts = [page.extract_text() or "" for page in reader.pages]
        internal_links = [_internal_link_count(page) for page in reader.pages]
    except (OSError, ValueError, PdfReadError) as exc:
        raise ComponentProofError("A readable PDF and pypdf are required") from exc
    if output.get("checks", {}).get("pages") != len(page_texts):
        raise ComponentProofError("Build report page count differs from PDF")
    result = validate_feature_evidence(plan, page_texts, internal_links)
    return result | {"family_id": plan["family_id"], "output_id": plan["output_id"],
                     "page_count": len(page_texts), "plan_sha256": _sha256(plan_path),
                     "build_report_sha256": _sha256(report_path), "pdf_sha256": pdf_hash,
                     "pdf_path": str(pdf), "internal_link_count": sum(internal_links),
                     "limit": "Text and internal-link evidence does not establish visual quality or publication readiness."}
