"""Static, versioned dispatch for family-owned declarative accent geometry.

Recipe versions select a closed set of built-in helpers. No module name, code,
asset, font, palette, or family default comes from the recipe. Legacy 0.1.0
serialization passes straight through to its original six-kind implementation.
"""
from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from .comic_accents import svg_accent, tikz_accent, validate_accent


RECIPE_VERSIONS = ("0.1.0", "0.2.0", "0.3.0")
COMIC_KINDS = frozenset({"motion-bars", "crosshair", "halftone", "burst", "orbit", "caption-frame"})
NARRATIVE_KINDS = frozenset({"trajectory-fan", "registration-tab"})
FINISH_KINDS = frozenset({"scratch-slashes", "cut-keyline"})
TECHNICAL_KINDS = frozenset({"concentric-rings", "signal-rule"})
ACCENT_KINDS_BY_VERSION = MappingProxyType({
    "0.1.0": COMIC_KINDS,
    "0.2.0": COMIC_KINDS | NARRATIVE_KINDS | FINISH_KINDS,
    "0.3.0": COMIC_KINDS | NARRATIVE_KINDS | FINISH_KINDS | TECHNICAL_KINDS,
})


def accent_backend(kind: str, recipe_version: str) -> dict[str, str]:
    """Describe one fixed backend after checking its explicit version boundary."""
    if not isinstance(recipe_version, str) or recipe_version not in RECIPE_VERSIONS:
        raise ValueError("Unsupported composition recipe version: {!r}; supported: {}".format(
            recipe_version, ", ".join(RECIPE_VERSIONS)))
    if not isinstance(kind, str) or kind not in ACCENT_KINDS_BY_VERSION[recipe_version]:
        raise ValueError("Accent kind {!r} is not supported by recipe {}".format(kind, recipe_version))
    if kind in COMIC_KINDS:
        module, validator, tikz, svg = "comic_accents", "validate_accent", "tikz_accent", "svg_accent"
    elif kind in NARRATIVE_KINDS:
        module, validator, tikz, svg = "narrative_marks", "validate_narrative_mark", "tikz_narrative_mark", "svg_narrative_mark"
    elif kind in FINISH_KINDS:
        module, validator, tikz, svg = "comic_finishes", "validate_finish", "tikz_finish", "svg_finish"
    else:
        module, validator, tikz, svg = "technical_marks", "validate_technical_mark", "tikz_technical_mark", "svg_technical_mark"
    return {"kind": kind, "recipe_version": recipe_version,
            "source_path": "src/sheepfling_styling/" + module + ".py",
            "validator": "sheepfling_styling." + module + "." + validator,
            "tikz_generator": "sheepfling_styling." + module + "." + tikz,
            "svg_generator": "sheepfling_styling." + module + "." + svg}


def _backend(recipe: Mapping[str, Any], recipe_version: str) -> dict[str, str]:
    if not isinstance(recipe, Mapping):
        raise ValueError("Accent recipe must be an object")
    return accent_backend(recipe.get("kind"), recipe_version)


def validate_recipe_accent(recipe: Mapping[str, Any], recipe_version: str) -> dict[str, Any]:
    """Validate and normalize through the kind's bounded native helper."""
    backend = _backend(recipe, recipe_version)
    if backend["kind"] in COMIC_KINDS:
        return validate_accent(recipe)
    if backend["kind"] in NARRATIVE_KINDS:
        from .narrative_marks import validate_narrative_mark
        return validate_narrative_mark(recipe)
    if backend["kind"] in TECHNICAL_KINDS:
        from .technical_marks import validate_technical_mark
        return validate_technical_mark(recipe)
    from .comic_finishes import validate_finish
    return validate_finish(recipe)


def tikz_recipe_accent(recipe: Mapping[str, Any], recipe_version: str) -> str:
    """Emit native TikZ without changing legacy six-kind bytes."""
    backend = _backend(recipe, recipe_version)
    if backend["kind"] in COMIC_KINDS:
        return tikz_accent(recipe)
    if backend["kind"] in NARRATIVE_KINDS:
        from .narrative_marks import narrative_mark, tikz_narrative_mark
        return tikz_narrative_mark(narrative_mark(recipe))
    if backend["kind"] in TECHNICAL_KINDS:
        from .technical_marks import tikz_technical_mark
        return tikz_technical_mark(recipe)
    from .comic_finishes import tikz_finish
    return tikz_finish(recipe)


def svg_recipe_accent(recipe: Mapping[str, Any], palette: Mapping[str, str], recipe_version: str) -> str:
    """Emit editable SVG using only the explicitly supplied semantic palette."""
    backend = _backend(recipe, recipe_version)
    if backend["kind"] in COMIC_KINDS:
        return svg_accent(recipe, palette)
    if backend["kind"] in NARRATIVE_KINDS:
        from .narrative_marks import narrative_mark, svg_narrative_mark
        return svg_narrative_mark(narrative_mark(recipe), palette)
    if backend["kind"] in TECHNICAL_KINDS:
        from .technical_marks import svg_technical_mark
        return svg_technical_mark(recipe,palette)
    from .comic_finishes import svg_finish
    return svg_finish(recipe, palette)


def describe_recipe_accent(recipe: Mapping[str, Any], recipe_version: str) -> dict[str, Any]:
    """Record exact grammar, implementation, and geometry-only label anchors."""
    result: dict[str, Any] = _backend(recipe, recipe_version)
    result["normalized_recipe"] = validate_recipe_accent(recipe, recipe_version)
    result["label_anchors"] = []
    if result["kind"] in NARRATIVE_KINDS:
        from .narrative_marks import narrative_mark
        result["label_anchors"] = [
            {"name": anchor.name, "x_mm": anchor.x_mm, "y_mm": anchor.y_mm, "alignment": anchor.alignment}
            for anchor in narrative_mark(recipe).label_anchors
        ]
    return result
