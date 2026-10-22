"""Validate source-pinned browser review evidence for a static web output."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from .customer_intake import IntakeError, pinned_file, read_intake
from .family_character import FamilyCharacterError, validate_family_character

REQUIRED_WIDTHS = {320, 390, 768, 1280}
CHECK_KEYS = {"reflow", "images", "computed_fonts", "keyboard_focus", "reduced_motion", "links", "contrast"}
CHECK_VALUES = {"passed", "not-applicable", "failed"}


class WebReviewError(ValueError):
    """A browser review record is incomplete, stale, or contradictory."""


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 2048:
        raise WebReviewError(f"{label} must be non-empty text")
    return value


def _pin(root: Path, record: Any, label: str) -> Path:
    try:
        return pinned_file(root, record, label)
    except IntakeError as exc:
        raise WebReviewError(str(exc)) from exc


def validate_web_review_receipt(path: Path, expected_entry_sha256: str | None = None) -> dict[str, Any]:
    try:
        data = read_intake(path)
    except IntakeError as exc:
        raise WebReviewError(str(exc)) from exc
    fields = {"schema_version", "status", "reviewer", "reviewed_at", "intended_use", "browser", "entry", "sources", "viewports", "family_character", "blocking_findings", "limitations"}
    if set(data) != fields or data["schema_version"] != "0.1.0" or not isinstance(data["status"], str) or data["status"] not in {"passed", "blocked"}:
        raise WebReviewError("Unsupported web review receipt structure or status")
    _text(data["reviewer"], "reviewer")
    _text(data["intended_use"], "intended_use")
    try:
        date.fromisoformat(data["reviewed_at"])
    except (TypeError, ValueError) as exc:
        raise WebReviewError("reviewed_at must be an ISO date") from exc
    browser = data["browser"]
    if not isinstance(browser, dict) or set(browser) != {"name", "version"}:
        raise WebReviewError("browser must identify its name and version")
    _text(browser["name"], "browser.name")
    _text(browser["version"], "browser.version")
    root = path.parent
    try:
        character = validate_family_character(data["family_character"], root, data["status"] == "passed")
    except FamilyCharacterError as exc:
        raise WebReviewError(str(exc)) from exc
    entry = _pin(root, data["entry"], "entry")
    if entry.suffix.lower() != ".html":
        raise WebReviewError("Web review entry must be HTML")
    if expected_entry_sha256 is not None and data["entry"]["sha256"] != expected_entry_sha256:
        raise WebReviewError("Web review entry hash differs from coverage output")
    sources = data["sources"]
    if not isinstance(sources, list) or not sources:
        raise WebReviewError("Web review must pin its linked source files")
    source_paths: set[str] = set()
    for index, record in enumerate(sources):
        source = _pin(root, record, f"sources[{index}]")
        if source == entry or str(source) in source_paths:
            raise WebReviewError("Web review source files must be distinct from the entry and each other")
        source_paths.add(str(source))
    for label in ("blocking_findings", "limitations"):
        if not isinstance(data[label], list) or any(not isinstance(value, str) or not value.strip() for value in data[label]):
            raise WebReviewError(f"{label} must be a list of non-empty text")
    viewports = data["viewports"]
    if not isinstance(viewports, list) or len(viewports) < len(REQUIRED_WIDTHS):
        raise WebReviewError("Web review needs every required responsive width")
    widths: set[int] = set()
    for index, record in enumerate(viewports):
        if not isinstance(record, dict) or set(record) != {"width", "height", "screenshot", "checks"}:
            raise WebReviewError(f"viewports[{index}] has missing or extra fields")
        width, height = record["width"], record["height"]
        if type(width) is not int or type(height) is not int or not 240 <= width <= 3840 or not 240 <= height <= 3840 or width in widths:
            raise WebReviewError("Viewport widths must be unique positive device sizes")
        widths.add(width)
        screenshot = _pin(root, record["screenshot"], f"viewports[{index}].screenshot")
        try:
            from PIL import Image
            with Image.open(screenshot) as image:
                if image.format != "PNG" or image.size != (width, height):
                    raise WebReviewError(f"Viewport {width} screenshot must be a matching PNG")
                image.verify()
        except (ImportError, OSError, ValueError) as exc:
            raise WebReviewError(f"Viewport {width} screenshot needs a readable PNG and Pillow") from exc
        checks = record["checks"]
        if not isinstance(checks, dict) or set(checks) != CHECK_KEYS or any(not isinstance(value, str) or value not in CHECK_VALUES for value in checks.values()):
            raise WebReviewError(f"Viewport {width} needs every declared browser check")
        if data["status"] == "passed":
            if any(value == "failed" for value in checks.values()) or any(checks[key] != "passed" for key in ("reflow", "computed_fonts", "contrast")):
                raise WebReviewError(f"Viewport {width} cannot pass with failed or unreviewed core checks")
    if not REQUIRED_WIDTHS.issubset(widths):
        raise WebReviewError("Web review omits a required responsive width")
    if data["status"] == "passed" and data["blocking_findings"]:
        raise WebReviewError("Passed web review may not have blocking findings")
    return {"status": data["status"], "reviewer": data["reviewer"],
            "reviewed_at": data["reviewed_at"], "browser": browser,
            "entry_sha256": data["entry"]["sha256"], "widths": sorted(widths),
            "family_character": character,
            "blocking_findings": len(data["blocking_findings"])}
