"""Measured, identity-free outlines for tightly stacked display typography.

Coordinates are millimetres with positive y down. A positive angle rises to
the right: ``x' = cos(a)*x + sin(a)*y; y' = -sin(a)*x + cos(a)*y``. Rotation is
about the layout origin, so returned bounds may contain negative coordinates.
Renderers supply actual font measurements; this module never estimates text.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

Point = tuple[float, float]
Rectangle = tuple[float, float, float, float]


class LockupGeometryError(ValueError):
    """A measured lockup cannot produce one bounded, connected silhouette."""


def _number(value: Any, name: str, lower: float, upper: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LockupGeometryError(f"{name} must be a finite number between {lower} and {upper}")
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise LockupGeometryError(f"{name} must be a finite number between {lower} and {upper}") from exc
    if not math.isfinite(result) or not lower <= result <= upper:
        raise LockupGeometryError(f"{name} must be a finite number between {lower} and {upper}")
    return result


def _outline(rectangles: tuple[Rectangle, ...]) -> tuple[Point, ...]:
    """Trace the orthogonal rectangle union, retaining its measured steps.

    The bounded coordinate grid splits shared edges before cancelling them.
    This handles overlapping rows and unequal widths without a convex hull,
    which would erase the deliberate line indents.
    """
    xs = sorted({x for x0, _, x1, _ in rectangles for x in (x0, x1)})
    ys = sorted({y for _, y0, _, y1 in rectangles for y in (y0, y1)})
    edges: set[tuple[Point, Point]] = set()
    for x0, x1 in zip(xs, xs[1:]):
        for y0, y1 in zip(ys, ys[1:]):
            if not any(left <= x0 and x1 <= right and top <= y0 and y1 <= bottom
                       for left, top, right, bottom in rectangles):
                continue
            corners = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
            for start, end in zip(corners, corners[1:] + corners[:1]):
                if (end, start) in edges:
                    edges.remove((end, start))
                else:
                    edges.add((start, end))

    outgoing: dict[Point, Point] = {}
    for start, end in edges:
        if start in outgoing:
            raise LockupGeometryError("rows must form one silhouette without point contacts or holes")
        outgoing[start] = end
    first = min(outgoing, key=lambda point: (point[1], point[0]))
    points = [first]
    next_point = outgoing[first]
    while next_point != first:
        points.append(next_point)
        if len(points) > len(edges) or next_point not in outgoing:
            raise LockupGeometryError("rows must form one closed silhouette")
        next_point = outgoing[next_point]
    if len(points) != len(edges):
        raise LockupGeometryError("rows must form one silhouette without holes")

    # Remove split-grid vertices along straight edges. Keep the clockwise
    # winding (in y-down coordinates) and deterministic top-left start.
    points = [point for index, point in enumerate(points)
              if not ((points[index - 1][0] == point[0] == points[(index + 1) % len(points)][0])
                      or (points[index - 1][1] == point[1] == points[(index + 1) % len(points)][1]))]
    first_index = min(range(len(points)), key=lambda index: (points[index][1], points[index][0]))
    return tuple(points[first_index:] + points[:first_index])


def measure_lockup(
    lines: Sequence[Mapping[str, Any]], *, angle_degrees: float = 4.0,
    padding_mm: float = 1.0, extrusion_mm: float = 0.0,
) -> dict[str, Any]:
    """Return a stepped outline, rotated geometry, and total transformed bounds.

    Supply 1..8 measured rows, in ascending ``y_mm`` order, with exactly
    ``width_mm``, ``height_mm``, ``x_mm``, and ``y_mm``. Dimensions are positive
    and at most 300 mm; origins accept -300..300 mm. Each padded row must
    overlap the preceding row horizontally and touch or overlap it vertically.
    Gaps are errors: the silhouette must stay connected without filling an
    arbitrary bridge between lines.

    ``outline`` and ``shadow_outline`` use the input coordinates. The optional
    shadow is offset by ``extrusion_mm`` down and right before rotation; draw it
    first. ``transformed_outline`` and ``transformed_shadow_outline`` include
    the angle. ``bounds_mm`` is ``(x_min, y_min, x_max, y_max)`` for both rotated
    polygons; ``width_mm`` and ``height_mm`` are its extents. Polygons omit a
    repeated closing vertex. No input is mutated.
    """
    if not isinstance(lines, Sequence) or isinstance(lines, (str, bytes)) or not 1 <= len(lines) <= 8:
        raise LockupGeometryError("lines must contain between 1 and 8 measured row objects")
    angle = _number(angle_degrees, "angle_degrees", -20.0, 20.0)
    padding = _number(padding_mm, "padding_mm", 0.0, 6.0)
    extrusion = _number(extrusion_mm, "extrusion_mm", 0.0, 6.0)
    rectangles: list[Rectangle] = []
    last_y: float | None = None
    for index, line in enumerate(lines):
        if not isinstance(line, Mapping) or set(line) != {"width_mm", "height_mm", "x_mm", "y_mm"}:
            raise LockupGeometryError("each row requires only width_mm, height_mm, x_mm, and y_mm")
        width = _number(line["width_mm"], f"lines[{index}].width_mm", 0.0, 300.0)
        height = _number(line["height_mm"], f"lines[{index}].height_mm", 0.0, 300.0)
        if width == 0.0 or height == 0.0:
            raise LockupGeometryError("row width_mm and height_mm must be positive")
        x = _number(line["x_mm"], f"lines[{index}].x_mm", -300.0, 300.0)
        y = _number(line["y_mm"], f"lines[{index}].y_mm", -300.0, 300.0)
        if last_y is not None and y < last_y:
            raise LockupGeometryError("rows must be supplied in ascending y_mm order")
        rectangle = (x - padding, y - padding, x + width + padding, y + height + padding)
        if rectangles:
            previous = rectangles[-1]
            if (rectangle[1] > previous[3]
                    or min(rectangle[2], previous[2]) <= max(rectangle[0], previous[0])):
                raise LockupGeometryError("adjacent padded rows must touch or overlap vertically and overlap horizontally")
        rectangles.append(rectangle)
        last_y = y

    outline = _outline(tuple(rectangles))
    shadow = tuple((x + extrusion, y + extrusion) for x, y in outline) if extrusion else None
    radians = math.radians(angle)
    cosine, sine = math.cos(radians), math.sin(radians)

    def rotate(points: tuple[Point, ...]) -> tuple[Point, ...]:
        return tuple((cosine * x + sine * y, -sine * x + cosine * y) for x, y in points)

    transformed = rotate(outline)
    transformed_shadow = rotate(shadow) if shadow else None
    all_points = transformed + (transformed_shadow or ())
    x_min, y_min = min(x for x, _ in all_points), min(y for _, y in all_points)
    x_max, y_max = max(x for x, _ in all_points), max(y for _, y in all_points)
    return {"outline": outline, "shadow_outline": shadow,
            "transformed_outline": transformed, "transformed_shadow_outline": transformed_shadow,
            "bounds_mm": (x_min, y_min, x_max, y_max),
            "width_mm": x_max - x_min, "height_mm": y_max - y_min}


def polygon_tikz(points: Sequence[Sequence[float]]) -> str:
    """Return a closed TikZ path with explicit mm units and no raw code input.

    Coordinates retain the y-down convention; use inside a ``yscale=-1`` scope
    (or negate y in a renderer that uses the conventional TikZ y-up system).
    This returns geometry only, without fill, stroke, colors, or a semicolon.
    """
    if not isinstance(points, Sequence) or isinstance(points, (str, bytes)) or not 3 <= len(points) <= 128:
        raise LockupGeometryError("polygon must contain between 3 and 128 coordinate pairs")

    def formatted(value: Any) -> str:
        number = _number(value, "polygon coordinate", -1000.0, 1000.0)
        text = f"{number:.6f}".rstrip("0").rstrip(".")
        return "0" if text in {"", "-0"} else text

    coordinates = []
    for point in points:
        if not isinstance(point, Sequence) or isinstance(point, (str, bytes)) or len(point) != 2:
            raise LockupGeometryError("polygon points must be coordinate pairs")
        coordinates.append(f"({formatted(point[0])}mm,{formatted(point[1])}mm)")
    return " -- ".join(coordinates) + " -- cycle"
