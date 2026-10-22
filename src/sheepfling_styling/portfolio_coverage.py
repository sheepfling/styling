"""Summarize six isolated profile slots without silently filling evidence gaps."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .customer_intake import IntakeError, load_and_validate_intake, pinned_file, read_intake
from .pdf_review_receipt import ReviewError, validate_pdf_review_receipt
from .web_review_receipt import WebReviewError, validate_web_review_receipt

EVIDENCE_VERSION = "0.1.0"
SLOT_FIELDS = {"status", "context", "input", "output", "review", "browser", "approval", "print", "reason"}
STATUSES = {"not-started", "built-awaiting-review", "reviewed", "unavailable-with-reason", "approved"}


class CoverageError(ValueError):
    """Portfolio evidence is inconsistent with the shared output contract."""


def _default_slot() -> dict[str, Any]:
    return {"status": "not-started", "context": "light", "input_sha256": None,
            "output_sha256": None, "review_sha256": None, "browser_sha256": None,
            "approval_sha256": None, "print_sha256": None, "reason": "No current evidence"}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = read_intake(path)
    except IntakeError as exc:
        raise CoverageError(str(exc)) from exc
    return value


def _pin(root: Path, record: Any, label: str) -> str:
    try:
        pinned_file(root, record, label)
    except IntakeError as exc:
        raise CoverageError(str(exc)) from exc
    return record["sha256"]


def _slot(raw: Any, root: Path, slot_id: str, is_web: bool) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != SLOT_FIELDS:
        raise CoverageError(f"{slot_id} must declare exactly the coverage slot fields")
    status = raw["status"]
    if not isinstance(status, str) or status not in STATUSES or raw["context"] != "light":
        raise CoverageError(f"{slot_id} has an unsupported status or non-light baseline context")
    result = {"status": status, "context": "light", "input_sha256": None,
              "output_sha256": None, "review_sha256": None, "browser_sha256": None,
              "approval_sha256": None, "print_sha256": None, "reason": None}
    if status == "not-started":
        if any(raw[key] is not None for key in SLOT_FIELDS - {"status", "context"}):
            raise CoverageError(f"{slot_id} cannot attach evidence to not-started")
        result["reason"] = "No current evidence"
        return result
    if status == "unavailable-with-reason":
        if not isinstance(raw["reason"], str) or not raw["reason"].strip() or any(raw[key] is not None for key in SLOT_FIELDS - {"status", "context", "reason"}):
            raise CoverageError(f"{slot_id} unavailable status requires only a reason")
        result["reason"] = raw["reason"]
        return result
    if raw["reason"] is not None:
        raise CoverageError(f"{slot_id} built output cannot have an unavailable reason")
    for key in ("input", "output"):
        result[f"{key}_sha256"] = _pin(root, raw[key], f"{slot_id}.{key}")
    if status in {"reviewed", "approved"}:
        review_key = "browser" if is_web else "review"
        result[f"{review_key}_sha256"] = _pin(root, raw[review_key], f"{slot_id}.{review_key}")
        try:
            review_path = pinned_file(root, raw[review_key], f"{slot_id}.{review_key}")
            review = (validate_web_review_receipt(review_path, result["output_sha256"]) if is_web
                      else validate_pdf_review_receipt(review_path, result["output_sha256"]))
        except (IntakeError, ReviewError, WebReviewError) as exc:
            raise CoverageError(f"{slot_id} review: {exc}") from exc
        if review["status"] != "passed":
            raise CoverageError(f"{slot_id} cannot advance with a blocked review")
    if status == "approved":
        result["approval_sha256"] = _pin(root, raw["approval"], f"{slot_id}.approval")
    for key in ("review", "browser", "approval"):
        if raw[key] is not None and result[f"{key}_sha256"] is None:
            raise CoverageError(f"{slot_id}.{key} is inconsistent with its status")
    if raw["print"] is not None:
        if is_web:
            raise CoverageError("Web output cannot claim a print receipt")
        result["print_sha256"] = _pin(root, raw["print"], f"{slot_id}.print")
    return result


def _registry_slots(repo_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    registry = _read_json(repo_root / "profiles/registry.json")
    suite = _read_json(repo_root / "contracts/typography-deliverable-suite.json")
    profiles = registry.get("profiles")
    slots = suite.get("family_output_parity", {}).get("required_slots")
    if not isinstance(profiles, list) or not isinstance(slots, list) or not slots:
        raise CoverageError("Registry and typography suite must declare profiles and required slots")
    ids = [item.get("profile_id") for item in profiles if isinstance(item, dict)]
    if len(ids) != len(profiles) or len(set(ids)) != len(ids) or len(profiles) != 6:
        raise CoverageError("Portfolio registry must contain six distinct profile slots")
    if len(set(slots)) != len(slots) or set(slots) != {item["id"] for item in suite["baseline_outputs"]}:
        raise CoverageError("Required output slots disagree with the typography suite")
    for item in profiles:
        path = repo_root / item["path"]
        if not path.resolve().is_relative_to(repo_root.resolve()) or not path.is_file():
            raise CoverageError("Registry profile path is missing or escapes the repository")
        profile = _read_json(path)
        if profile.get("profile_id") != item["profile_id"] or profile.get("status") != item["status"]:
            raise CoverageError("Registry profile identity or status differs from its file")
    return profiles, slots


def build_portfolio_report(repo_root: Path, evidence_dir: Path | None = None,
                           intake_dir: Path | None = None) -> dict[str, Any]:
    """Return customer-neutral per-slot coverage, validating supplied exact bytes."""
    repo_root = repo_root.resolve()
    profiles, slot_ids = _registry_slots(repo_root)
    for directory, label in ((evidence_dir, "evidence"), (intake_dir, "intake")):
        if directory is not None and not directory.is_dir():
            raise CoverageError(f"{label} directory does not exist: {directory}")
    rows: list[dict[str, Any]] = []
    counts = {status: 0 for status in sorted(STATUSES)}
    for entry in profiles:
        profile_id = entry["profile_id"]
        intake_summary = None
        if intake_dir is not None:
            intake_path = intake_dir / f"{profile_id}.json"
            if intake_path.is_file():
                try:
                    intake_summary = load_and_validate_intake(intake_path)
                except IntakeError as exc:
                    raise CoverageError(f"{profile_id} intake: {exc}") from exc
                if intake_summary["profile_id"] != profile_id:
                    raise CoverageError(f"{profile_id} intake has a different profile id")
        slots = {slot_id: _default_slot() for slot_id in slot_ids}
        if evidence_dir is not None:
            evidence_path = evidence_dir / f"{profile_id}.json"
            if evidence_path.is_file():
                data = _read_json(evidence_path)
                if set(data) != {"schema_version", "profile_id", "slots"} or data["schema_version"] != EVIDENCE_VERSION or data["profile_id"] != profile_id or not isinstance(data["slots"], dict):
                    raise CoverageError(f"{profile_id} has invalid coverage evidence headers")
                if not set(data["slots"]).issubset(slot_ids):
                    raise CoverageError(f"{profile_id} declares an unknown baseline slot")
                for slot_id, raw in data["slots"].items():
                    slots[slot_id] = _slot(raw, evidence_path.parent, slot_id, slot_id == "web-light")
        if any(slot["status"] == "approved" for slot in slots.values()) and not (intake_summary and intake_summary["profile_ready"]):
            raise CoverageError(f"{profile_id} approved outputs require a validated profile-ready intake")
        for slot in slots.values():
            counts[slot["status"]] += 1
        rows.append({"profile_id": profile_id, "registry_status": entry["status"],
                     "intake": intake_summary, "slots": slots})
    return {"schema_version": EVIDENCE_VERSION, "profile_count": len(rows),
            "required_slots": slot_ids, "slot_count": len(rows) * len(slot_ids),
            "status_counts": counts, "profiles": rows,
            "summary": {"reviewed_or_approved_slots": counts["reviewed"] + counts["approved"],
                        "profiles_with_valid_intake": sum(row["intake"] is not None for row in rows),
                        "profile_ready_count": sum(bool(row["intake"] and row["intake"]["profile_ready"]) for row in rows)}}
