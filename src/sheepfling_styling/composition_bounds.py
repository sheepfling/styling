"""Identity-free placement checks for measured native composition polygons.

These checks guard declared geometry, not inferred font outlines or raster
transparency. Coordinates are millimetres with positive y down; positive
rotation rises to the right, matching the lockup geometry helper.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

Point = tuple[float, float]
_EPS = 1e-8


class PlacementError(ValueError):
    """A placement is malformed or violates its explicit region/clearances."""


def _number(value: Any, name: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PlacementError(f"{name} must be a finite number in {low}..{high}")
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise PlacementError(f"{name} must be a finite number in {low}..{high}") from exc
    if not math.isfinite(result) or not low <= result <= high:
        raise PlacementError(f"{name} must be a finite number in {low}..{high}")
    return result


def _sequence(value: Any, count: int | None = None) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) and (count is None or len(value) == count)


def _cross(a: Point, b: Point, c: Point) -> float:
    return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])


def _on(a: Point, b: Point, point: Point) -> bool:
    return (abs(_cross(a,b,point)) <= _EPS and min(a[0],b[0])-_EPS <= point[0] <= max(a[0],b[0])+_EPS
            and min(a[1],b[1])-_EPS <= point[1] <= max(a[1],b[1])+_EPS)


def _intersects(a: Point, b: Point, c: Point, d: Point) -> bool:
    ac, ad, ca, cb = _cross(a,b,c), _cross(a,b,d), _cross(c,d,a), _cross(c,d,b)
    return ((ac > _EPS and ad < -_EPS or ac < -_EPS and ad > _EPS)
            and (ca > _EPS and cb < -_EPS or ca < -_EPS and cb > _EPS)) or any(
                (_on(a,b,c), _on(a,b,d), _on(c,d,a), _on(c,d,b)))


def _polygon(points: Any) -> tuple[Point, ...]:
    if not _sequence(points) or not 3 <= len(points) <= 128:
        raise PlacementError("polygon must have 3..128 points without a repeated closing vertex")
    result = []
    for point in points:
        if not _sequence(point, 2):
            raise PlacementError("polygon points must be coordinate pairs")
        result.append((_number(point[0], "point x", -100000,100000), _number(point[1], "point y", -100000,100000)))
    edges = list(zip(result, result[1:] + result[:1]))
    if any(a == b for a,b in edges):
        raise PlacementError("polygon contains an empty edge")
    area = sum(a[0]*b[1]-b[0]*a[1] for a,b in edges)
    if abs(area) <= _EPS:
        raise PlacementError("polygon must enclose positive area")
    for i, (a,b) in enumerate(edges):
        for j, (c,d) in enumerate(edges[i+1:], i+1):
            if j == i+1 or i == 0 and j == len(edges)-1:
                continue
            if _intersects(a,b,c,d):
                raise PlacementError("polygon must be simple, without self-intersection or point contacts")
    return tuple(result)


def _rectangle(value: Any, name: str) -> tuple[float, float, float, float]:
    if not _sequence(value, 4):
        raise PlacementError(f"{name} requires x, y, width, height in millimetres")
    x, y = (_number(value[i], name, -100000,100000) for i in (0,1))
    w, h = (_number(value[i], name, .001,10000) for i in (2,3))
    return x,y,w,h


def _contains(points: tuple[Point, ...], p: Point) -> bool:
    inside = False
    for a,b in zip(points, points[1:]+points[:1]):
        if _on(a,b,p):
            return True
        if (a[1] > p[1]) != (b[1] > p[1]) and p[0] < (b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]:
            inside = not inside
    return inside


def transform_outline(points: Sequence[Sequence[float]], *, origin_mm: Sequence[float] = (0,0),
                      scale_x: float = 1, scale_y: float = 1, angle_degrees: float = 0) -> tuple[Point, ...]:
    """Scale locally, rotate about the origin, then translate, exactly once."""
    polygon = _polygon(points)
    if not _sequence(origin_mm, 2):
        raise PlacementError("origin_mm requires two coordinates")
    tx, ty = (_number(value, "origin_mm", -10000,10000) for value in origin_mm)
    sx = _number(scale_x, "scale_x", .1,8)
    sy = _number(scale_y, "scale_y", .1,8)
    angle = math.radians(_number(angle_degrees, "angle_degrees", -180,180))
    c, s = math.cos(angle), math.sin(angle)
    return _polygon(tuple((tx+c*sx*x+s*sy*y, ty-s*sx*x+c*sy*y) for x,y in polygon))


def guard_placement(points: Sequence[Sequence[float]], *, region_mm: Sequence[float],
                    clearance_mm: float = 0, obstacles: Sequence[Sequence[float]] = ()) -> dict[str, Any]:
    """Check polygon against an enclosing region and rectangular obstacles.

    Region edges permit exact contact at the declared clearance. Obstacle
    contact is rejected, including corner/edge tangency. Clearance expands
    obstacle rectangles on all sides. Concave notches are preserved rather
    than rejected solely because their bounding box overlaps an obstacle.
    """
    polygon = _polygon(points)
    x,y,w,h = region = _rectangle(region_mm, "region_mm")
    margin = _number(clearance_mm, "clearance_mm", 0,20)
    if not _sequence(obstacles) or len(obstacles) > 64:
        raise PlacementError("obstacles must contain at most 64 rectangles")
    boxes = tuple(_rectangle(box, f"obstacle {index}") for index,box in enumerate(obstacles))
    left, top = min(p[0] for p in polygon), min(p[1] for p in polygon)
    right, bottom = max(p[0] for p in polygon), max(p[1] for p in polygon)
    if left < x+margin-_EPS or top < y+margin-_EPS or right > x+w-margin+_EPS or bottom > y+h-margin+_EPS:
        raise PlacementError(f"transformed bounds {(left,top,right,bottom)} exceed region {region} with clearance {margin} mm")
    edges = tuple(zip(polygon, polygon[1:]+polygon[:1]))
    for index, (ox,oy,ow,oh) in enumerate(boxes):
        l,t,r,b = ox-margin, oy-margin, ox+ow+margin, oy+oh+margin
        corners = ((l,t),(r,t),(r,b),(l,b))
        if (any(l-_EPS <= px <= r+_EPS and t-_EPS <= py <= b+_EPS for px,py in polygon)
                or any(_contains(polygon, corner) for corner in corners)
                or any(_intersects(a,c,d,e) for a,c in edges for d,e in zip(corners,corners[1:]+corners[:1]))):
            raise PlacementError(f"transformed polygon touches or overlaps obstacle {index} at clearance {margin} mm")
    return {"status": "passed", "bounds_mm": (left,top,right,bottom), "region_mm": region,
            "clearance_mm": margin, "checked_obstacles": len(boxes)}
