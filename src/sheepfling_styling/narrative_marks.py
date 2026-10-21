"""Identity-free narrative fans and technical tabs as measured native vectors.

All coordinates are millimetres, positive y up. Profiles supply colors and
copy; label anchors are geometry metadata only. SVG and TikZ consume exactly
the same deterministic immutable primitive stream.
"""
from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from xml.sax.saxutils import quoteattr


class NarrativeMarkError(ValueError):
    """A mark recipe or export palette is outside the bounded grammar."""


@dataclass(frozen=True)
class Primitive:
    kind: str
    points: tuple[float, ...]
    fill: str | None
    stroke: str | None
    stroke_mm: float


@dataclass(frozen=True)
class LabelAnchor:
    name: str
    x_mm: float
    y_mm: float
    alignment: str


@dataclass(frozen=True)
class NarrativeMark:
    kind: str
    width_mm: float
    height_mm: float
    shapes: tuple[Primitive, ...]
    label_anchors: tuple[LabelAnchor, ...]


_DEFAULTS = {
    "trajectory-fan": {"stroke_mm": .3, "arms": 4, "node_radius_mm": .9},
    "registration-tab": {"stroke_mm": .3, "cut_mm": 2.0, "rail_width_mm": 5.0,
                         "registration_radius_mm": .8},
}
_SEMANTIC = {"ink": "BGInk", "page": "BGPage", "accent": "BGAccent", "line": "BGLine"}
_HEX = re.compile(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\Z")


def _number(value: Any, name: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise NarrativeMarkError(f"{name} must be a finite number in {low}..{high}")
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise NarrativeMarkError(f"{name} must be a finite number in {low}..{high}") from exc
    if not math.isfinite(result) or not low <= result <= high:
        raise NarrativeMarkError(f"{name} must be a finite number in {low}..{high}")
    return result


def validate_narrative_mark(recipe: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a closed recipe with explicit physical dimensions.

    Width is 16..180 mm; height 16..120 mm; strokes are .25..1.5 mm.
    Fans accept 3..5 arms and .6..2.5 mm hollow-node radii. Tabs accept
    cut_mm (1..6), rail_width_mm (3..12), and registration_radius_mm (.6..2).
    Geometry-dependent limits preserve clear terminal gaps and open tab space.
    """
    if not isinstance(recipe, Mapping) or set(recipe) - {"kind", "width_mm", "height_mm", "parameters"}:
        raise NarrativeMarkError("mark requires only kind, width_mm, height_mm, and optional parameters")
    kind = recipe.get("kind")
    if not isinstance(kind, str) or kind not in _DEFAULTS:
        raise NarrativeMarkError("unsupported narrative mark kind")
    width = _number(recipe.get("width_mm"), "width_mm", 16, 180)
    height = _number(recipe.get("height_mm"), "height_mm", 16, 120)
    supplied = recipe.get("parameters", {})
    if not isinstance(supplied, Mapping) or set(supplied) - set(_DEFAULTS[kind]):
        raise NarrativeMarkError("unsupported parameters for narrative mark")
    parameters = {**_DEFAULTS[kind], **supplied}
    parameters["stroke_mm"] = _number(parameters["stroke_mm"], "stroke_mm", .25, 1.5)
    if kind == "trajectory-fan":
        arms = parameters["arms"]
        if isinstance(arms, bool) or not isinstance(arms, int) or not 3 <= arms <= 5:
            raise NarrativeMarkError("arms must be an integer in 3..5")
        radius = parameters["node_radius_mm"] = _number(parameters["node_radius_mm"], "node_radius_mm", .6, 2.5)
        if 2*radius + parameters["stroke_mm"] >= .65*height/(arms-1):
            raise NarrativeMarkError("terminal nodes must retain a clear gap, including stroke")
        if radius + parameters["stroke_mm"]/2 > min(.15*height,.245*width):
            raise NarrativeMarkError("terminal nodes including stroke must fit the mark bounds")
    else:
        parameters["cut_mm"] = _number(parameters["cut_mm"], "cut_mm", 1, min(6, .27*min(width,height)))
        parameters["rail_width_mm"] = _number(parameters["rail_width_mm"], "rail_width_mm", 3, min(12, .35*width))
        parameters["registration_radius_mm"] = _number(parameters["registration_radius_mm"], "registration_radius_mm", .6, 2)
        if parameters["registration_radius_mm"] + parameters["stroke_mm"] > 2.5:
            raise NarrativeMarkError("registration circle and stroke must fit the corner clearance")
    return {"kind": kind, "width_mm": width, "height_mm": height, "parameters": parameters}


def narrative_mark(recipe: Mapping[str, Any]) -> NarrativeMark:
    """Generate a bounded fan or tab; anchors contain no rendered labels."""
    normalized = validate_narrative_mark(recipe)
    kind, width, height, p = (normalized[key] for key in ("kind", "width_mm", "height_mm", "parameters"))
    stroke = p["stroke_mm"]
    shapes, anchors = [], []

    def shape(kind, points, fill=None, edge="ink"):
        shapes.append(Primitive(kind, tuple(points), fill, edge, stroke))

    if kind == "trajectory-fan":
        for index in range(p["arms"]):
            sx, sy = (.10 + .025*index)*width, (.10 + .025*index)*height
            nx, ny = (.72 + .035*(index % 2))*width, (.85 - .65*index/(p["arms"]-1))*height
            radius = p["node_radius_mm"]
            end = nx - radius
            shape("cubic", (sx, sy, sx + .20*width, sy + .55*(ny-sy), end-.14*width, ny, end, ny))
            shape("circle", (nx, ny, radius), "page")
            shape("circle", (sx, sy, stroke*.75), "accent", None)
            anchors.append(LabelAnchor(f"terminal-{index+1}", nx+radius+.035*width, ny, "west"))
    else:
        pad, cut, rail = max(.75, stroke), p["cut_mm"], p["rail_width_mm"]
        shape("polygon", (pad,pad, width-pad-cut,pad, width-pad,pad+cut,
                          width-pad,height-pad, pad+cut,height-pad, pad,height-pad-cut), "page")
        shape("line", (pad+rail,pad, pad+rail,height-pad), edge="line")
        shape("line", (pad+rail+1.5,pad+2, width-pad-3,pad+2), edge="accent")
        cx, cy, radius = width-pad-3, height-pad-3, p["registration_radius_mm"]
        shape("circle", (cx,cy,radius), "page")
        shape("line", (cx-1.8,cy,cx+1.8,cy))
        shape("line", (cx,cy-1.8,cx,cy+1.8))
        anchors.extend((LabelAnchor("index", pad+rail/2, height/2, "center"),
                        LabelAnchor("caption", pad+rail+2, height/2, "west")))
    mark = NarrativeMark(kind,width,height,tuple(shapes),tuple(anchors))
    _field(mark)
    return mark


def _f(value: float) -> str:
    result = f"{value:.6f}".rstrip("0").rstrip(".")
    return "0" if result in {"", "-0"} else result


def _field(mark: NarrativeMark) -> None:
    if not isinstance(mark, NarrativeMark) or not isinstance(mark.kind,str) or mark.kind not in _DEFAULTS:
        raise NarrativeMarkError("export requires a generated NarrativeMark")
    width = _number(mark.width_mm,"width_mm",16,180)
    height = _number(mark.height_mm,"height_mm",16,120)
    if not isinstance(mark.shapes, tuple) or not 1 <= len(mark.shapes) <= 15:
        raise NarrativeMarkError("mark must contain a bounded immutable primitive stream")
    for item in mark.shapes:
        if not isinstance(item, Primitive) or not isinstance(item.kind,str) or item.kind not in {"line","cubic","circle","polygon"}:
            raise NarrativeMarkError("unsupported mark primitive")
        expected = {"line":4,"cubic":8,"circle":3,"polygon":12}[item.kind]
        if not isinstance(item.points, tuple) or len(item.points) != expected:
            raise NarrativeMarkError("invalid primitive point count")
        if any(value is not None and (not isinstance(value,str) or value not in _SEMANTIC)
               for value in (item.fill,item.stroke)):
            raise NarrativeMarkError("primitive colors must be semantic")
        _number(item.stroke_mm,"stroke_mm",.25,1.5)
        for value in item.points:
            _number(value,"coordinate",0,max(width,height))
        if item.kind == "circle":
            cx,cy,r = item.points
            edge = item.stroke_mm/2 if item.stroke else 0
            if r <= 0 or cx-r-edge < 0 or cx+r+edge > width or cy-r-edge < 0 or cy+r+edge > height:
                raise NarrativeMarkError("circle must remain inside mark bounds")
        elif any(not item.stroke_mm/2 <= x <= width-item.stroke_mm/2 or not item.stroke_mm/2 <= y <= height-item.stroke_mm/2
                 for x,y in zip(item.points[::2],item.points[1::2])):
            raise NarrativeMarkError("primitive must remain inside mark bounds")
    if not isinstance(mark.label_anchors,tuple) or len(mark.label_anchors)>5:
        raise NarrativeMarkError("label anchors must be a bounded immutable tuple")
    for anchor in mark.label_anchors:
        if not isinstance(anchor,LabelAnchor) or not isinstance(anchor.name,str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,31}",anchor.name):
            raise NarrativeMarkError("label anchors require safe metadata names")
        _number(anchor.x_mm,"label x",0,width)
        _number(anchor.y_mm,"label y",0,height)
        if not isinstance(anchor.alignment,str) or anchor.alignment not in {"west","center"}:
            raise NarrativeMarkError("label anchor alignment must be west or center")


def tikz_narrative_mark(mark: NarrativeMark) -> str:
    """Return a complete clipped TikZ picture with semantic profile colors."""
    _field(mark)
    width,height = _f(mark.width_mm),_f(mark.height_mm)
    lines = [r"\begin{tikzpicture}[x=1mm,y=1mm,line cap=round,line join=round]",
             rf"\path[use as bounding box] (0,0) rectangle ({width},{height});",
             rf"\clip (0,0) rectangle ({width},{height});"]
    for primitive in mark.shapes:
        values = primitive.points
        style = "fill="+(_SEMANTIC[primitive.fill] if primitive.fill else "none")+",draw="+(_SEMANTIC[primitive.stroke] if primitive.stroke else "none")
        if primitive.stroke:
            style += ",line width="+_f(primitive.stroke_mm)+"mm"
        pairs = [f"({_f(x)},{_f(y)})" for x,y in zip(values[::2],values[1::2])]
        if primitive.kind == "circle":
            path = f"({_f(values[0])},{_f(values[1])}) circle[radius={_f(values[2])}mm]"
        elif primitive.kind == "cubic":
            path = f"{pairs[0]} .. controls {pairs[1]} and {pairs[2]} .. {pairs[3]}"
        else:
            path = " -- ".join(pairs)+(" -- cycle" if primitive.kind == "polygon" else "")
        lines.append(f"% narrative primitive {primitive.kind}")
        lines.append(rf"\path[{style}] {path};")
    lines.append(r"\end{tikzpicture}")
    return "\n".join(lines)+"\n"


def svg_narrative_mark(mark: NarrativeMark, palette: Mapping[str,str]) -> str:
    """Return a standalone SVG; require explicit ink/page/accent/line hex colors."""
    _field(mark)
    if not isinstance(palette,Mapping) or set(palette) != set(_SEMANTIC) or any(not isinstance(value,str) or not _HEX.fullmatch(value) for value in palette.values()):
        raise NarrativeMarkError("palette requires explicit ink/page/accent/line hex colors")
    width,height = _f(mark.width_mm),_f(mark.height_mm)
    clip = "narrative-"+width.replace(".","p")+"-"+height.replace(".","p")
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" height="{height}mm" viewBox="0 0 {width} {height}">',
             f'<defs><clipPath id="{clip}"><rect width="{width}" height="{height}"/></clipPath></defs>',
             f'<g clip-path="url(#{clip})"><g transform="translate(0 {height}) scale(1 -1)" stroke-linecap="round" stroke-linejoin="round">']
    for primitive in mark.shapes:
        values = primitive.points
        attrs = {"fill":palette[primitive.fill] if primitive.fill else "none", "stroke":palette[primitive.stroke] if primitive.stroke else "none"}
        if primitive.stroke:
            attrs["stroke-width"] = _f(primitive.stroke_mm)
        tag = primitive.kind
        if tag == "cubic":
            tag = "path"
            attrs["d"] = "M "+" ".join(map(_f,values[:2]))+" C "+" ".join(map(_f,values[2:]))
        elif tag == "polygon":
            attrs["points"] = " ".join(f"{_f(x)},{_f(y)}" for x,y in zip(values[::2],values[1::2]))
        else:
            attrs.update(zip(("cx","cy","r") if tag == "circle" else ("x1","y1","x2","y2"),map(_f,values)))
        lines.append("<"+tag+" "+" ".join(key+"="+quoteattr(value) for key,value in attrs.items())+"/>")
    lines.extend(("</g></g>","</svg>"))
    return "\n".join(lines)+"\n"
