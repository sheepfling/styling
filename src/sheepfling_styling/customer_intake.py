"""Validate profile-owned source and readiness intake without importing customer data."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_VERSION = "0.1.0"
SHA = re.compile(r"[0-9a-f]{64}\Z")
PROFILE = re.compile(r"system-[0-9]{2}\Z")
IDENTIFIER = re.compile(r"[a-z][a-z0-9-]*\Z")
REQUIRED_FACES = {"body", "display", "strong"}
OPTIONAL_FACES = {"wordmark", "mono"}
EVIDENCE_KEYS = {"design_approval", "proof_review", "production_approval", "publication_clearance"}


class IntakeError(ValueError):
    """The intake claims unsupported state or references missing or changed bytes."""


def _object(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise IntakeError(f"{label} must contain exactly {', '.join(sorted(keys))}")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 2048:
        raise IntakeError(f"{label} must be non-empty text of at most 2048 characters")
    return value


def _choice(value: Any, choices: set[str], label: str) -> str:
    if not isinstance(value, str) or value not in choices:
        raise IntakeError(f"{label} has an unsupported value")
    return value


def read_intake(path: Path) -> dict[str, Any]:
    """Read a bounded JSON intake, rejecting duplicate keys before validation."""
    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise IntakeError(f"Duplicate intake key: {key}")
            result[key] = value
        return result

    try:
        if path.stat().st_size > 1_048_576:
            raise IntakeError("Intake exceeds 1 MiB")
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IntakeError(f"Cannot read intake: {path}") from exc
    if not isinstance(value, dict):
        raise IntakeError("Intake must be a JSON object")
    return value


def pinned_file(root: Path, record: Any, label: str) -> Path:
    """Resolve one exact byte record inside the intake/evidence directory."""
    item = _object(record, {"path", "sha256"}, label)
    relative = item["path"]
    digest = item["sha256"]
    if (not isinstance(relative, str) or not relative or "\\" in relative
            or not re.fullmatch(r"[A-Za-z0-9_./-]+", relative)):
        raise IntakeError(f"{label}.path must be a safe relative path")
    posix = PurePosixPath(relative)
    if posix.is_absolute() or any(part in {".", ".."} for part in relative.split("/")) or "//" in relative:
        raise IntakeError(f"{label}.path escapes its evidence directory")
    if not isinstance(digest, str) or not SHA.fullmatch(digest):
        raise IntakeError(f"{label}.sha256 must be lowercase SHA-256")
    root = root.resolve()
    candidate = root / relative
    for ancestor in (candidate, *candidate.parents):
        if ancestor == root:
            break
        if ancestor.is_symlink():
            raise IntakeError(f"{label}.path may not use symlinks")
    path = candidate.resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise IntakeError(f"{label}.path does not resolve inside its evidence directory")
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise IntakeError(f"{label} bytes differ from the declared SHA-256")
    return path


def validate_intake(data: Any, root: Path) -> dict[str, Any]:
    """Validate source pins and state dependencies; return a neutral summary."""
    item = _object(data, {"schema_version", "profile_id", "source_owner", "route", "sources", "typefaces", "claims", "states", "evidence"}, "intake")
    if item["schema_version"] != SCHEMA_VERSION:
        raise IntakeError("Unsupported customer-intake schema version")
    profile_id = item["profile_id"]
    if not isinstance(profile_id, str) or not PROFILE.fullmatch(profile_id):
        raise IntakeError("profile_id must be a system-XX slot")
    _text(item["source_owner"], "source_owner")
    route = _object(item["route"], {"status", "name"}, "route")
    _choice(route["status"], {"pending", "selected", "approved"}, "route.status")
    _text(route["name"], "route.name")

    sources = item["sources"]
    if not isinstance(sources, list) or not sources:
        raise IntakeError("sources must contain at least one exact source record")
    by_id: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(sources):
        source = _object(raw, {"id", "kind", "origin", "file", "rights", "publish"}, f"sources[{index}]")
        source_id = source["id"]
        if not isinstance(source_id, str) or not IDENTIFIER.fullmatch(source_id) or source_id in by_id:
            raise IntakeError("Source ids must be unique lowercase identifiers")
        _choice(source["kind"], {"artwork", "font", "copy", "reference"}, f"sources[{index}].kind")
        _text(source["origin"], f"sources[{index}].origin")
        pinned_file(root, source["file"], f"sources[{index}].file")
        rights = _object(source["rights"], {"status", "basis", "redistribution", "evidence"}, f"sources[{index}].rights")
        _choice(rights["status"], {"pending", "verified"}, f"sources[{index}].rights.status")
        _choice(rights["redistribution"], {"unknown", "allowed", "restricted", "prohibited"}, f"sources[{index}].rights.redistribution")
        _text(rights["basis"], f"sources[{index}].rights.basis")
        if rights["status"] == "verified":
            pinned_file(root, rights["evidence"], f"sources[{index}].rights.evidence")
        elif rights["evidence"] is not None or rights["redistribution"] == "allowed":
            raise IntakeError(f"Pending rights cannot claim verified evidence or allowed redistribution: {source_id}")
        if type(source["publish"]) is not bool:
            raise IntakeError(f"sources[{index}].publish must be boolean")
        by_id[source_id] = source

    typefaces = _object(item["typefaces"], {"status", "bindings"}, "typefaces")
    if not isinstance(typefaces["status"], str) or typefaces["status"] not in {"unresolved", "selected"} or not isinstance(typefaces["bindings"], dict):
        raise IntakeError("Unsupported typeface selection")
    bindings = typefaces["bindings"]
    if typefaces["status"] == "unresolved" and bindings:
        raise IntakeError("Unresolved typefaces may not claim selected bindings")
    if typefaces["status"] == "selected":
        if not REQUIRED_FACES.issubset(bindings) or not set(bindings).issubset(REQUIRED_FACES | OPTIONAL_FACES):
            raise IntakeError("Selected typefaces need body, display, and strong bindings")
        for face, source_id in bindings.items():
            if not isinstance(source_id, str) or source_id not in by_id or by_id[source_id]["kind"] != "font":
                raise IntakeError(f"Typeface {face} must bind a declared font source")

    claims = item["claims"]
    if not isinstance(claims, list):
        raise IntakeError("claims must be a list")
    claim_ids: set[str] = set()
    for index, raw in enumerate(claims):
        claim = _object(raw, {"id", "text", "source_ids", "status", "approval"}, f"claims[{index}]")
        if not isinstance(claim["id"], str) or not IDENTIFIER.fullmatch(claim["id"]) or claim["id"] in claim_ids:
            raise IntakeError("Claim ids must be unique lowercase identifiers")
        claim_ids.add(claim["id"])
        _text(claim["text"], f"claims[{index}].text")
        if not isinstance(claim["source_ids"], list) or not claim["source_ids"] or any(not isinstance(source_id, str) or source_id not in by_id for source_id in claim["source_ids"]):
            raise IntakeError("Every claim must cite declared source ids")
        _choice(claim["status"], {"pending", "approved"}, f"claims[{index}].status")
        if claim["status"] == "approved":
            pinned_file(root, claim["approval"], f"claims[{index}].approval")
        elif claim["approval"] is not None:
            raise IntakeError("Pending claims may not have approval evidence")

    states = _object(item["states"], {"local_proof", "production", "publication"}, "states")
    _choice(states["local_proof"], {"not-started", "built", "reviewed"}, "states.local_proof")
    _choice(states["production"], {"not-ready", "candidate", "approved"}, "states.production")
    _choice(states["publication"], {"not-cleared", "pending", "cleared"}, "states.publication")
    evidence = _object(item["evidence"], EVIDENCE_KEYS, "evidence")
    required_evidence = {
        "design_approval": route["status"] == "approved",
        "proof_review": states["local_proof"] == "reviewed",
        "production_approval": states["production"] == "approved",
        "publication_clearance": states["publication"] == "cleared",
    }
    for key, required in required_evidence.items():
        if required:
            pinned_file(root, evidence[key], f"evidence.{key}")
        elif evidence[key] is not None:
            raise IntakeError(f"evidence.{key} is not supported by the current status")
    if states["local_proof"] == "reviewed" and route["status"] != "approved":
        raise IntakeError("Reviewed proof requires an approved route")
    if states["production"] != "not-ready" and states["local_proof"] != "reviewed":
        raise IntakeError("Production candidacy requires a reviewed local proof")
    if states["publication"] != "not-cleared" and route["status"] != "approved":
        raise IntakeError("Publication review requires an approved route")
    if states["publication"] == "cleared":
        if any(source["publish"] and (source["rights"]["status"] != "verified" or source["rights"]["redistribution"] != "allowed") for source in sources):
            raise IntakeError("Publication clearance requires verified redistribution rights for every published source")
        if any(claim["status"] != "approved" for claim in claims):
            raise IntakeError("Publication clearance requires approved claims")

    profile_ready = (route["status"] == "approved" and typefaces["status"] == "selected"
                     and all(source["rights"]["status"] == "verified" for source in sources))
    return {"profile_id": profile_id, "schema_version": SCHEMA_VERSION,
            "source_count": len(sources), "claim_count": len(claims), "profile_ready": profile_ready,
            "route_status": route["status"], "typeface_status": typefaces["status"],
            "local_proof": states["local_proof"], "production": states["production"],
            "publication": states["publication"]}


def load_and_validate_intake(path: Path) -> dict[str, Any]:
    return validate_intake(read_intake(path), path.parent)
