"""Show every shared output slot without inferring missing family work."""
from __future__ import annotations

from typing import Any

BASELINE_SLOTS = ("document-one-page", "document-two-page", "web-light", "product-slick", "component-proof")


def coverage_from_outputs(outputs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    coverage = {}
    for slot in BASELINE_SLOTS:
        matching = [item["id"] for item in outputs if item.get("slot") == slot and item.get("context") == "light"]
        coverage[slot] = {"status": "built-awaiting-visual-review" if matching else "not-run", "outputs": matching}
    return coverage
