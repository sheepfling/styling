"""Require visual reviews to account for a family's declared signature features."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .customer_intake import IntakeError, pinned_file

DISPOSITIONS = {"preserved", "adapted", "missing"}


class FamilyCharacterError(ValueError):
    """The family-character review is incomplete or cannot support a pass."""


def validate_family_character(value: Any, root: Path, passed: bool) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"reference", "features"}:
        raise FamilyCharacterError("family_character needs a pinned reference and feature reviews")
    try:
        pinned_file(root, value["reference"], "family_character.reference")
    except IntakeError as exc:
        raise FamilyCharacterError(str(exc)) from exc
    features = value["features"]
    if not isinstance(features, list) or not features:
        raise FamilyCharacterError("family_character needs at least one signature feature")
    names: set[str] = set()
    dispositions: dict[str, int] = {name: 0 for name in sorted(DISPOSITIONS)}
    for index, feature in enumerate(features):
        if not isinstance(feature, dict) or set(feature) != {"name", "disposition", "evidence"}:
            raise FamilyCharacterError(f"family_character.features[{index}] has missing or extra fields")
        name, disposition, evidence = (feature[key] for key in ("name", "disposition", "evidence"))
        if any(not isinstance(text, str) or not text.strip() or len(text) > 2048 for text in (name, evidence)):
            raise FamilyCharacterError("Family feature names and evidence must be non-empty text")
        if name in names:
            raise FamilyCharacterError("Family feature names must be distinct")
        if not isinstance(disposition, str) or disposition not in DISPOSITIONS:
            raise FamilyCharacterError("Family feature disposition is unsupported")
        names.add(name)
        dispositions[disposition] += 1
    if passed and dispositions["missing"]:
        raise FamilyCharacterError("Passed review cannot leave a signature feature missing")
    return {"reference_sha256": value["reference"]["sha256"], "features": len(features),
            "dispositions": dispositions}
