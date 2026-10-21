"""Measured native dot fields from normalized luminance and optional coverage.

This module owns no image loading, crop decisions, palette, identity, or copy.
An adapter supplies a small rectangular top-to-bottom lightness grid. The
result is immutable geometry that both SVG and TikZ serialize without loops,
embedded images, linked resources, or renderer-side tone calculations.
"""
from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from xml.sax.saxutils import quoteattr


class TonalHalftoneError(ValueError):
    """A luminance field or native export argument is outside the grammar."""


MAX_SAMPLES = 1200
MAX_AXIS_SAMPLES = 64
_MIN_SERIALIZED_RADIUS_MM = 0.000000001
_HEX = re.compile(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\Z")


@dataclass(frozen=True, slots=True)
class TonalHalftone:
    """Circles in millimetres and y-up coordinates, ordered by source rows."""

    width_mm: float
    height_mm: float
    rows: int
    columns: int
    circles: tuple[tuple[float, float, float], ...]

    @property
    def sample_count(self) -> int:
        return self.rows * self.columns

    @property
    def circle_count(self) -> int:
        return len(self.circles)


def _number(value: Any, name: str, lower: float, upper: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TonalHalftoneError(f"{name} must be a finite number between {lower} and {upper}")
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise TonalHalftoneError(f"{name} must be a finite number between {lower} and {upper}") from exc
    if not math.isfinite(result) or not lower <= result <= upper:
        raise TonalHalftoneError(f"{name} must be a finite number between {lower} and {upper}")
    return result


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _grid(values: Any, name: str) -> tuple[tuple[float, ...], ...]:
    if not _is_sequence(values) or not 1 <= len(values) <= MAX_AXIS_SAMPLES:
        raise TonalHalftoneError(f"{name} must have 1..{MAX_AXIS_SAMPLES} rectangular rows")
    first = values[0]
    if not _is_sequence(first) or not 1 <= len(first) <= MAX_AXIS_SAMPLES:
        raise TonalHalftoneError(f"{name} must have 1..{MAX_AXIS_SAMPLES} columns")
    columns = len(first)
    if len(values) * columns > MAX_SAMPLES:
        raise TonalHalftoneError(f"{name} must contain at most {MAX_SAMPLES} samples")
    normalized = []
    for index, row in enumerate(values):
        if not _is_sequence(row) or len(row) != columns:
            raise TonalHalftoneError(f"{name} must be rectangular")
        normalized.append(tuple(_number(value, f"{name}[{index}][{column}]", 0.0, 1.0)
                                for column, value in enumerate(row)))
    return tuple(normalized)


def tonal_halftone(
    tones: Sequence[Sequence[float]],
    *,
    width_mm: float,
    height_mm: float,
    dot_min_mm: float = 0.02,
    dot_max_mm: float = 0.65,
    gamma: float = 1.0,
    invert: bool = False,
    coverage: Sequence[Sequence[float]] | None = None,
) -> TonalHalftone:
    """Turn 0..1 lightness into a bounded native vector circle stream.

    Input row zero is the image's top row. Darkness is ``1-tone`` (or ``tone``
    when inverted); white and fully transparent samples emit no circle.
    For nonzero darkness, squared radius is::

        coverage * (minimum_radius**2
                    + (maximum_radius**2 - minimum_radius**2) * darkness**gamma)

    Thus coverage scales actual ink area, rather than scaling the diameter.
    The maximum radius is capped at 46% of the smaller cell pitch and the
    minimum is scaled by the same factor, preserving contrast when reduced.
    Width/height are 1..500 mm, radii 0..5 mm (maximum must be positive), and
    gamma 0.1..5. At most 64 rows, 64 columns, and 1200 samples are accepted.
    """
    width = _number(width_mm, "width_mm", 1.0, 500.0)
    height = _number(height_mm, "height_mm", 1.0, 500.0)
    minimum = _number(dot_min_mm, "dot_min_mm", 0.0, 5.0)
    maximum = _number(dot_max_mm, "dot_max_mm", 0.001, 5.0)
    exponent = _number(gamma, "gamma", 0.1, 5.0)
    if minimum > maximum:
        raise TonalHalftoneError("dot_min_mm must not exceed dot_max_mm")
    if not isinstance(invert, bool):
        raise TonalHalftoneError("invert must be a boolean")
    luminance = _grid(tones, "tones")
    rows, columns = len(luminance), len(luminance[0])
    alpha = _grid(coverage, "coverage") if coverage is not None else None
    if alpha is not None and (len(alpha) != rows or len(alpha[0]) != columns):
        raise TonalHalftoneError("coverage must have the same shape as tones")
    pitch_x, pitch_y = width / columns, height / rows
    capped_maximum = min(maximum, 0.46 * min(pitch_x, pitch_y))
    minimum, maximum = minimum * (capped_maximum / maximum), capped_maximum
    low_area, area_range = minimum * minimum, maximum * maximum - minimum * minimum
    circles = []
    for row_index, row in enumerate(luminance):
        for column_index, tone in enumerate(row):
            darkness = tone if invert else 1.0 - tone
            opacity = alpha[row_index][column_index] if alpha is not None else 1.0
            if darkness == 0.0 or opacity == 0.0:
                continue
            radius = min(maximum, math.sqrt(opacity * (low_area + area_range * darkness ** exponent)))
            # Omit circles below export precision so the immutable stream and
            # both serialized outputs always contain the same number of dots.
            if radius >= _MIN_SERIALIZED_RADIUS_MM:
                circles.append(((column_index + 0.5) * pitch_x,
                                height - (row_index + 0.5) * pitch_y, radius))
    return TonalHalftone(width, height, rows, columns, tuple(circles))


def corner_halftone(
    *, width_mm: float, height_mm: float, corner: str,
    columns: int = 32, rows: int = 32, fade_radius_ratio: float = 1.05,
    dot_min_mm: float = 0.02, dot_max_mm: float = 0.62,
) -> TonalHalftone:
    """Create a synthetic two-dimensional smoothstep corner dissolve.

    The named corner is in page coordinates (top/bottom, left/right).
    Distance is normalized by field width/height; coverage, hence dot area,
    fades to zero at ``fade_radius_ratio``. This is designed geometry, not
    sampled image tone. Both exports consume the existing bounded stream.
    """
    if not isinstance(corner, str) or corner not in {"top-left", "top-right", "bottom-left", "bottom-right"}:
        raise TonalHalftoneError("corner must be top-left, top-right, bottom-left, or bottom-right")
    if any(isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= MAX_AXIS_SAMPLES for n in (rows, columns)) or rows*columns > MAX_SAMPLES:
        raise TonalHalftoneError("corner grid exceeds the bounded sample grid")
    radius = _number(fade_radius_ratio, "fade_radius_ratio", 0.25, 1.5)
    corner_x, corner_y = (1 if corner.endswith("right") else 0), (1 if corner.startswith("bottom") else 0)
    coverage = []
    for row in range(rows):
        values = []
        for column in range(columns):
            distance = math.hypot((column+.5)/columns-corner_x, (row+.5)/rows-corner_y)
            t = min(1.0, distance/radius)
            values.append(1-t*t*(3-2*t))
        coverage.append(values)
    return tonal_halftone([[0.0]*columns for _ in range(rows)], width_mm=width_mm, height_mm=height_mm,
                          dot_min_mm=dot_min_mm, dot_max_mm=dot_max_mm, coverage=coverage)


def _validate_field(field: TonalHalftone) -> None:
    # The dataclass is public, so exports also reject malformed hand-built
    # point streams instead of trusting that the factory created the object.
    if not isinstance(field, TonalHalftone):
        raise TonalHalftoneError("field must be a TonalHalftone")
    width = _number(field.width_mm, "width_mm", 1.0, 500.0)
    height = _number(field.height_mm, "height_mm", 1.0, 500.0)
    if any(isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_AXIS_SAMPLES
           for value in (field.rows, field.columns)) or field.sample_count > MAX_SAMPLES:
        raise TonalHalftoneError("field dimensions exceed the bounded sample grid")
    if not isinstance(field.circles, tuple) or len(field.circles) > field.sample_count:
        raise TonalHalftoneError("field circles must be an immutable bounded point stream")
    ceiling = min(5.0, 0.46 * min(width / field.columns, height / field.rows))
    for circle in field.circles:
        if not isinstance(circle, tuple) or len(circle) != 3:
            raise TonalHalftoneError("each circle must be an (x_mm, y_mm, radius_mm) tuple")
        x = _number(circle[0], "circle x", 0.0, width)
        y = _number(circle[1], "circle y", 0.0, height)
        radius = _number(circle[2], "circle radius", _MIN_SERIALIZED_RADIUS_MM, ceiling)
        if x - radius < 0 or x + radius > width or y - radius < 0 or y + radius > height:
            raise TonalHalftoneError("circle must have positive radius and remain within the field")


def _f(value: float) -> str:
    # Nine decimal places preserve tiny alpha dots and physical placement.
    formatted = f"{value:.9f}".rstrip("0").rstrip(".")
    return "0" if formatted in {"", "-0"} else formatted


def _visible_circles(field: TonalHalftone) -> tuple[tuple[str, str, str], ...]:
    return tuple(tuple(map(_f, circle)) for circle in field.circles)


def tikz_tonal_halftone(field: TonalHalftone) -> str:
    """Return a full clipped TikZ picture using the owner's BGInk color.

    Every circle is an explicit subpath of one grouped native fill operation.
    There are no PGF calculations, iteration macros, or external resources.
    """
    _validate_field(field)
    width, height = _f(field.width_mm), _f(field.height_mm)
    output = [r"\begin{tikzpicture}[x=1mm,y=1mm]",
              rf"\path[use as bounding box] (0,0) rectangle ({width},{height});",
              rf"\clip (0,0) rectangle ({width},{height});"]
    circles = _visible_circles(field)
    if circles:
        output.append(r"\path[fill=BGInk,draw=none]")
        output.extend(f"  ({x},{y}) circle [radius={radius}mm]" for x, y, radius in circles)
        output[-1] += ";"
    output.append(r"\end{tikzpicture}")
    return "\n".join(output) + "\n"


def svg_tonal_halftone(field: TonalHalftone, color: str) -> str:
    """Return a standalone native SVG in an explicit #RGB or #RRGGBB ink."""
    _validate_field(field)
    if not isinstance(color, str) or not _HEX.fullmatch(color):
        raise TonalHalftoneError("color must be an explicit #RGB or #RRGGBB hex value")
    width, height = _f(field.width_mm), _f(field.height_mm)
    clip_id = "tone-box-" + width.replace(".", "p") + "-" + height.replace(".", "p")
    output = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" height="{height}mm" viewBox="0 0 {width} {height}">',
              f'<defs><clipPath id="{clip_id}"><rect width="{width}" height="{height}"/></clipPath></defs>',
              f'<g clip-path="url(#{clip_id})"><g transform="translate(0 {height}) scale(1 -1)" fill={quoteattr(color)} stroke="none">']
    output.extend(f'<circle cx="{x}" cy="{y}" r="{radius}"/>' for x, y, radius in _visible_circles(field))
    output.extend(["</g></g>", "</svg>"])
    return "\n".join(output) + "\n"
