"""Bounded, native vector accents shared by SVG and TikZ renderers.

Recipes contain geometry only. The owning visual profile supplies the four SVG
palette colors, or defines BGAccent/BGInk/BGPage/BGLine before using TikZ. No
fonts, copy, identity marks, linked assets, or profile defaults live here.

Dimensions use millimetres. All coordinates use a conventional y-up system;
the SVG wrapper flips that system once. Each renderer consumes the same shape
stream and clips to the exact recipe box, so the two exports remain editable.
"""
from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from xml.sax.saxutils import quoteattr


class AccentError(ValueError):
    """An accent recipe or palette cannot be rendered safely."""


KINDS = frozenset({"motion-bars", "crosshair", "halftone", "burst", "orbit", "caption-frame"})
_DEFAULTS: dict[str, dict[str, Any]] = {
    "motion-bars": {"count": 4, "slant": 0.35},
    "crosshair": {"radius_ratio": 0.32},
    "halftone": {"columns": 14, "rows": 8, "dot_min_mm": 0.08, "dot_max_mm": 0.7, "fade": "right"},
    "burst": {"rays": 12, "inner_ratio": 0.65, "rotation_degrees": 0.0},
    "orbit": {"rings": 2, "tilt_degrees": -20.0},
    "caption-frame": {"cut_mm": 2.0},
}
_NUMERIC_BOUNDS = {
    "stroke_mm": (0.08, 1.5), "slant": (0.0, 0.7), "radius_ratio": (0.15, 0.42),
    "dot_min_mm": (0.02, 0.7), "dot_max_mm": (0.08, 0.7),
    "inner_ratio": (0.45, 0.85), "rotation_degrees": (-180.0, 180.0),
    "tilt_degrees": (-45.0, 45.0), "cut_mm": (1.0, 4.0),
}
_INTEGER_BOUNDS = {"count": (3, 7), "columns": (8, 24), "rows": (4, 14), "rays": (8, 20), "rings": (1, 3)}
_COLORS = {"accent": "BGAccent", "ink": "BGInk", "page": "BGPage", "line": "BGLine"}
_HEX = re.compile(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\Z")


def _number(value: Any, name: str, lower: float, upper: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AccentError(f"{name} must be a finite number between {lower} and {upper}")
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise AccentError(f"{name} must be a finite number between {lower} and {upper}") from exc
    if not math.isfinite(result) or not lower <= result <= upper:
        raise AccentError(f"{name} must be a finite number between {lower} and {upper}")
    return result


def validate_accent(recipe: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an explicit recipe and return fresh, default-complete data.

    Required fields are kind, width_mm (6..160), and height_mm (6..100).
    Optional parameters accept stroke_mm (0.08..1.5) and the knobs in
    ``_DEFAULTS`` for that kind. Unknown fields are errors, never raw code.
    Dot sizes are radii; geometry caps them further to 46% of the cell pitch
    so even the densest small marks keep separate dots.
    """
    if not isinstance(recipe, Mapping):
        raise AccentError("accent recipe must be an object")
    if set(recipe) - {"kind", "width_mm", "height_mm", "parameters"}:
        raise AccentError("accent recipe contains unknown fields")
    kind = recipe.get("kind")
    if not isinstance(kind, str) or kind not in KINDS:
        raise AccentError("accent kind is not supported")
    width = _number(recipe.get("width_mm"), "width_mm", 6.0, 160.0)
    height = _number(recipe.get("height_mm"), "height_mm", 6.0, 100.0)
    supplied = recipe.get("parameters", {})
    if not isinstance(supplied, Mapping):
        raise AccentError("accent parameters must be an object")
    defaults = {"stroke_mm": 0.35, **_DEFAULTS[kind]}
    if set(supplied) - set(defaults):
        raise AccentError(f"unsupported parameters for {kind}")
    parameters = {**defaults, **supplied}
    for key, value in parameters.items():
        if key in _INTEGER_BOUNDS:
            lower, upper = _INTEGER_BOUNDS[key]
            if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
                raise AccentError(f"{key} must be an integer between {lower} and {upper}")
        elif key in _NUMERIC_BOUNDS:
            parameters[key] = _number(value, key, *_NUMERIC_BOUNDS[key])
        elif not isinstance(value, str) or value not in {"left", "right", "up", "down"}:
            raise AccentError("fade must be left, right, up, or down")
    if kind == "halftone" and parameters["dot_min_mm"] > parameters["dot_max_mm"]:
        raise AccentError("dot_min_mm must not exceed dot_max_mm")
    return {"kind": kind, "width_mm": width, "height_mm": height, "parameters": parameters}


@dataclass(frozen=True)
class _Shape:
    kind: str
    coordinates: tuple[float, ...]
    fill: str | None = None
    stroke: str | None = None
    stroke_mm: float = 0.0


def _geometry(recipe: dict[str, Any]) -> tuple[_Shape, ...]:
    """One measured primitive stream for both backends; never random."""
    width, height, parameters = recipe["width_mm"], recipe["height_mm"], recipe["parameters"]
    stroke = parameters["stroke_mm"]
    kind = recipe["kind"]
    shapes: list[_Shape] = []

    def polygon(points: list[tuple[float, float]], fill: str, edge: str | None = None) -> None:
        shapes.append(_Shape("polygon", tuple(v for point in points for v in point), fill, edge, stroke))

    def line(x1: float, y1: float, x2: float, y2: float, color: str = "ink") -> None:
        shapes.append(_Shape("line", (x1, y1, x2, y2), None, color, stroke))

    def ellipse(cx: float, cy: float, rx: float, ry: float, angle: float = 0.0,
                fill: str | None = None, edge: str | None = "ink") -> None:
        shapes.append(_Shape("ellipse", (cx, cy, rx, ry, angle), fill, edge, stroke))

    if kind == "motion-bars":
        y0, y1 = height * 0.2, height * 0.8
        skew = parameters["slant"] * min(y1 - y0, width * 0.22)
        step = (width * 0.88 - skew) / parameters["count"]
        for index in range(parameters["count"]):
            x = width * 0.06 + index * step
            bar_width = step * 0.76
            polygon([(x, y0), (x + bar_width, y0), (x + bar_width + skew, y1), (x + skew, y1)],
                    "ink" if index == parameters["count"] - 1 else "accent")
        line(width * 0.06, height * 0.12, width * 0.31, height * 0.12, "line")
    elif kind == "crosshair":
        radius = min(width, height) * parameters["radius_ratio"]
        ellipse(width / 2, height / 2, radius, radius)
        line(width * 0.08, height / 2, width * 0.92, height / 2)
        line(width / 2, height * 0.08, width / 2, height * 0.92)
        dot = min(width, height) * 0.035
        ellipse(width / 2, height / 2, dot, dot, fill="accent", edge=None)
    elif kind == "halftone":
        columns, rows = parameters["columns"], parameters["rows"]
        pitch_x, pitch_y = width / columns, height / rows
        ceiling = min(parameters["dot_max_mm"], min(pitch_x, pitch_y) * 0.46)
        floor = min(parameters["dot_min_mm"], ceiling)
        for row in range(rows):
            for column in range(columns):
                fade = parameters["fade"]
                progression = column / (columns - 1) if fade in {"left", "right"} else row / (rows - 1)
                if fade in {"left", "down"}:
                    progression = 1.0 - progression
                radius = floor + (ceiling - floor) * progression ** 1.45
                ellipse((column + 0.5) * pitch_x, (row + 0.5) * pitch_y, radius, radius, fill="ink", edge=None)
    elif kind == "burst":
        points = []
        for index in range(parameters["rays"] * 2):
            angle = math.radians(parameters["rotation_degrees"] + 180 * index / parameters["rays"])
            radius = 1.0 if index % 2 == 0 else parameters["inner_ratio"]
            points.append((width * (0.5 + 0.42 * radius * math.cos(angle)),
                           height * (0.51 + 0.42 * radius * math.sin(angle))))
        polygon([(x + width * 0.018, y - height * 0.025) for x, y in points], "accent")
        polygon(points, "page", "ink")
    elif kind == "orbit":
        count = parameters["rings"]
        node: tuple[float, float] | None = None
        for index in range(count):
            angle = parameters["tilt_degrees"] + (index - (count - 1) / 2) * 18
            radians = math.radians(angle)
            rx, ry = width * 0.43, height * 0.27
            horizontal = math.hypot(rx * math.cos(radians), ry * math.sin(radians))
            vertical = math.hypot(rx * math.sin(radians), ry * math.cos(radians))
            fit = min(width * 0.43 / horizontal, height * 0.40 / vertical)
            rx, ry = rx * fit, ry * fit
            ellipse(width / 2, height / 2, rx, ry, angle, edge="ink" if index == 0 else "line")
            if index == 0:
                dx, dy = rx * math.cos(0.55), ry * math.sin(0.55)
                node = (width / 2 + dx * math.cos(radians) - dy * math.sin(radians),
                        height / 2 + dx * math.sin(radians) + dy * math.cos(radians))
        dot = min(width, height) * 0.045
        ellipse(width / 2, height / 2, dot * 0.55, dot * 0.55, fill="ink", edge=None)
        assert node is not None
        ellipse(*node, dot, dot, fill="accent", edge="page")
    else:  # caption-frame: clipped opposing corners leave a quiet copy area.
        shadow = min(width * 0.015, height * 0.035)
        pad = max(stroke * 0.75, min(width, height) * 0.035) + shadow
        cut = min(parameters["cut_mm"], (min(width, height) - 2 * pad) * 0.24)
        points = [(pad, pad), (width - pad - cut, pad), (width - pad, pad + cut),
                  (width - pad, height - pad), (pad + cut, height - pad), (pad, height - pad - cut)]
        polygon([(x + shadow, y - shadow) for x, y in points], "accent")
        polygon(points, "page", "ink")
        line(pad + cut + stroke, height - pad - stroke * 2,
             min(width - pad - stroke, pad + cut + width * 0.2), height - pad - stroke * 2, "accent")
    return tuple(shapes)


def _f(value: float) -> str:
    formatted = f"{value:.6f}".rstrip("0").rstrip(".")
    return "0" if formatted in {"", "-0"} else formatted


def tikz_accent(recipe: Mapping[str, Any]) -> str:
    """Return a complete, clipped TikZ picture using profile semantic colors."""
    normalized = validate_accent(recipe)
    width, height = _f(normalized["width_mm"]), _f(normalized["height_mm"])
    output = [r"\begin{tikzpicture}[x=1mm,y=1mm,line cap=round,line join=round]",
              rf"\path[use as bounding box] (0,0) rectangle ({width},{height});",
              rf"\clip (0,0) rectangle ({width},{height});"]
    for shape in _geometry(normalized):
        output.append(f"% comic-accent primitive {shape.kind}")
        style = ["fill=" + (_COLORS[shape.fill] if shape.fill else "none"),
                 "draw=" + (_COLORS[shape.stroke] if shape.stroke else "none")]
        if shape.stroke:
            style.append("line width=" + _f(shape.stroke_mm) + "mm")
        options = ",".join(style)
        values = shape.coordinates
        if shape.kind == "polygon":
            path = " -- ".join(f"({_f(values[i])},{_f(values[i + 1])})" for i in range(0, len(values), 2))
            output.append(rf"\path[{options}] {path} -- cycle;")
        elif shape.kind == "line":
            output.append(rf"\path[{options}] ({_f(values[0])},{_f(values[1])}) -- ({_f(values[2])},{_f(values[3])});")
        else:
            cx, cy, rx, ry, angle = map(_f, values)
            output.extend([rf"\begin{{scope}}[shift={{({cx},{cy})}},rotate={angle}]",
                           rf"\path[{options}] (0,0) ellipse [x radius={rx}mm,y radius={ry}mm];",
                           r"\end{scope}"])
    output.append(r"\end{tikzpicture}")
    return "\n".join(output) + "\n"


def svg_accent(recipe: Mapping[str, Any], palette: Mapping[str, str]) -> str:
    """Return a standalone editable SVG with explicit hex profile colors."""
    normalized = validate_accent(recipe)
    if not isinstance(palette, Mapping) or set(palette) != set(_COLORS):
        raise AccentError("palette must explicitly define accent, ink, page, and line")
    for color in palette.values():
        if not isinstance(color, str) or not _HEX.fullmatch(color):
            raise AccentError("palette colors must be #RGB or #RRGGBB hex values")
    width, height = _f(normalized["width_mm"]), _f(normalized["height_mm"])
    # Several standalone exports can also be embedded in one SVG proof plate.
    # Equal boxes can share a clip definition; different boxes must not collide.
    clip_id = "accent-box-" + width.replace(".", "p") + "-" + height.replace(".", "p")
    output = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" height="{height}mm" viewBox="0 0 {width} {height}">',
              f'<defs><clipPath id="{clip_id}"><rect width="{width}" height="{height}"/></clipPath></defs>',
              f'<g clip-path="url(#{clip_id})"><g transform="translate(0 {height}) scale(1 -1)" stroke-linecap="round" stroke-linejoin="round">']
    for shape in _geometry(normalized):
        attributes = {"fill": palette[shape.fill] if shape.fill else "none",
                      "stroke": palette[shape.stroke] if shape.stroke else "none"}
        if shape.stroke:
            attributes["stroke-width"] = _f(shape.stroke_mm)
        values = shape.coordinates
        if shape.kind == "polygon":
            attributes["points"] = " ".join(f"{_f(values[i])},{_f(values[i + 1])}" for i in range(0, len(values), 2))
        elif shape.kind == "line":
            attributes.update(zip(("x1", "y1", "x2", "y2"), map(_f, values)))
        else:
            attributes.update(zip(("cx", "cy", "rx", "ry"), map(_f, values[:4])))
            if values[4]:
                attributes["transform"] = f"rotate({_f(values[4])} {_f(values[0])} {_f(values[1])})"
        output.append("<" + shape.kind + " " + " ".join(key + "=" + quoteattr(value) for key, value in attributes.items()) + "/>")
    output.extend(["</g></g>", "</svg>"])
    return "\n".join(output) + "\n"
