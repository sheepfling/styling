"""Bounded concentric rings and interrupted signal rules as native geometry.

The owning family supplies palette, copy, placement and intended-size review.
All coordinates are millimetres, positive y up. Hollow circles have no fill,
so both serializers preserve the substrate rather than painting page color.
"""
from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from xml.sax.saxutils import quoteattr


class TechnicalMarkError(ValueError):
    """A technical mark exceeds its closed physical grammar."""


@dataclass(frozen=True)
class TechnicalPrimitive:
    kind: str
    points: tuple[float, ...]
    stroke_mm: float


@dataclass(frozen=True)
class TechnicalMark:
    kind: str
    width_mm: float
    height_mm: float
    shapes: tuple[TechnicalPrimitive, ...]


_DEFAULTS = {
    "concentric-rings": {"stroke_mm": .25, "rings": 5, "inner_ratio": .2},
    "signal-rule": {"stroke_mm": .25, "lanes": 3, "node_radius_mm": .8, "gap_mm": 1.2},
}
_HEX = re.compile(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\Z")


def _number(value: Any, name: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TechnicalMarkError(f"{name} must be a finite number in {low}..{high}")
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise TechnicalMarkError(f"{name} must be finite") from exc
    if not math.isfinite(result) or not low <= result <= high:
        raise TechnicalMarkError(f"{name} must be a finite number in {low}..{high}")
    return result


def _integer(value: Any, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise TechnicalMarkError(f"{name} must be an integer in {low}..{high}")
    return value


def validate_technical_mark(recipe: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize rings (8..160 mm) or rules (20..180 by 6..48 mm).

    Rings accept 3..8 circles; strokes and concentric air gaps must fit.
    Rules accept 1..3 lanes with alternating hollow nodes. Gaps are measured
    between the visible circle stroke and each round line cap. Geometry
    constraints retain full strokes, separate lanes, and useful rule lengths.
    """
    if not isinstance(recipe, Mapping) or set(recipe)-{"kind", "width_mm", "height_mm", "parameters"}:
        raise TechnicalMarkError("mark requires only kind, width_mm, height_mm, parameters")
    kind = recipe.get("kind")
    if not isinstance(kind, str) or kind not in _DEFAULTS:
        raise TechnicalMarkError("unsupported technical mark kind")
    w = _number(recipe.get("width_mm"), "width_mm", 8 if kind=="concentric-rings" else 20, 160 if kind=="concentric-rings" else 180)
    h = _number(recipe.get("height_mm"), "height_mm", 8 if kind=="concentric-rings" else 6, 160 if kind=="concentric-rings" else 48)
    supplied = recipe.get("parameters", {})
    if not isinstance(supplied, Mapping) or set(supplied)-set(_DEFAULTS[kind]):
        raise TechnicalMarkError("unsupported technical mark parameters")
    p = {**_DEFAULTS[kind], **supplied}
    s = p["stroke_mm"] = _number(p["stroke_mm"], "stroke_mm", .15, 1.2)
    if kind=="concentric-rings":
        n = p["rings"] = _integer(p["rings"], "rings", 3, 8)
        ratio = p["inner_ratio"] = _number(p["inner_ratio"], "inner_ratio", .12, .5)
        outer = min(w,h)/2-max(.6,s)
        if outer*ratio <= s/2 or outer*(1-ratio)/(n-1)-s < .2:
            raise TechnicalMarkError("rings must retain an open center and at least .2 mm between strokes")
    else:
        n = p["lanes"] = _integer(p["lanes"], "lanes", 1, 3)
        r = p["node_radius_mm"] = _number(p["node_radius_mm"], "node_radius_mm", .6, 2.5)
        gap = p["gap_mm"] = _number(p["gap_mm"], "gap_mm", .5, 6)
        if r <= s/2 or r+s/2 > h*(.5 if n==1 else .25):
            raise TechnicalMarkError("hollow nodes including stroke must fit the rule field")
        if n>1 and .5*h/(n-1)-(2*r+s) < .35:
            raise TechnicalMarkError("rule lanes must retain at least .35 mm of air between nodes")
        if .25*w-r-gap-s-max(.75,s) < 2*s:
            raise TechnicalMarkError("node gaps must leave usable straight rule segments")
    return {"kind":kind, "width_mm":w, "height_mm":h, "parameters":p}


def technical_mark(recipe: Mapping[str, Any]) -> TechnicalMark:
    normalized = validate_technical_mark(recipe)
    kind,w,h,p = (normalized[k] for k in ("kind","width_mm","height_mm","parameters"))
    s = p["stroke_mm"]
    shapes = []
    if kind=="concentric-rings":
        outer = min(w,h)/2-max(.6,s)
        inner = outer*p["inner_ratio"]
        for i in range(p["rings"]):
            r = inner+(outer-inner)*i/(p["rings"]-1)
            shapes.append(TechnicalPrimitive("circle",(w/2,h/2,r),s))
    else:
        r, gap, n = p["node_radius_mm"],p["gap_mm"],p["lanes"]
        for i in range(n):
            x, y = (.75 if i%2==0 else .25)*w, (.5 if n==1 else .75-.5*i/(n-1))*h
            pad = max(.75,s)
            # Two half-strokes account for the circle edge and round line cap.
            shapes.extend((TechnicalPrimitive("line",(pad,y,x-r-gap-s,y),s),
                           TechnicalPrimitive("circle",(x,y,r),s),
                           TechnicalPrimitive("line",(x+r+gap+s,y,w-pad,y),s)))
    result = TechnicalMark(kind,w,h,tuple(shapes))
    _validate_stream(result)
    return result


def _validate_stream(mark: TechnicalMark) -> None:
    if not isinstance(mark,TechnicalMark) or not isinstance(mark.kind,str) or mark.kind not in _DEFAULTS:
        raise TechnicalMarkError("export requires a TechnicalMark or recipe")
    w = _number(mark.width_mm,"width_mm",8 if mark.kind=="concentric-rings" else 20,160 if mark.kind=="concentric-rings" else 180)
    h = _number(mark.height_mm,"height_mm",8 if mark.kind=="concentric-rings" else 6,160 if mark.kind=="concentric-rings" else 48)
    if not isinstance(mark.shapes,tuple) or not 1 <= len(mark.shapes) <= 9:
        raise TechnicalMarkError("primitive stream must be immutable and bounded")
    for shape in mark.shapes:
        if not isinstance(shape,TechnicalPrimitive) or not isinstance(shape.kind,str) or shape.kind not in {"circle","line"}:
            raise TechnicalMarkError("unsupported technical primitive")
        s = _number(shape.stroke_mm,"stroke_mm",.15,1.2)
        if not isinstance(shape.points,tuple) or len(shape.points)!=(3 if shape.kind=="circle" else 4):
            raise TechnicalMarkError("invalid primitive point count")
        for v in shape.points:
            _number(v,"coordinate",0,max(w,h))
        if shape.kind=="circle":
            x,y,r=shape.points
            if r<=s/2 or x-r-s/2<0 or y-r-s/2<0 or x+r+s/2>w or y+r+s/2>h:
                raise TechnicalMarkError("hollow circle and full stroke must fit the field")
        else:
            x,y,u,v=shape.points
            if (x,y)==(u,v) or any(not s/2<=a<=w-s/2 or not s/2<=b<=h-s/2 for a,b in ((x,y),(u,v))):
                raise TechnicalMarkError("line and round caps must fit the field")
    if mark.kind=="concentric-rings":
        if not 3<=len(mark.shapes)<=8 or any(s.kind!="circle" or s.points[:2]!=(w/2,h/2) for s in mark.shapes):
            raise TechnicalMarkError("rings must be concentric circles")
        if any(b.points[2]-a.points[2]-(a.stroke_mm+b.stroke_mm)/2 < .2-1e-9 for a,b in zip(mark.shapes,mark.shapes[1:])):
            raise TechnicalMarkError("rings must retain at least .2 mm between strokes")
    else:
        if len(mark.shapes)%3:
            raise TechnicalMarkError("each rule lane needs two lines and one hollow node")
        nodes=[]
        for left,node,right in zip(mark.shapes[::3],mark.shapes[1::3],mark.shapes[2::3]):
            if (left.kind,node.kind,right.kind)!=("line","circle","line"):
                raise TechnicalMarkError("invalid rule lane topology")
            x,y,r=node.points
            if any(abs(v-y)>1e-9 for v in (*left.points[1::2],*right.points[1::2])):
                raise TechnicalMarkError("rule segments must align with their node")
            gap_left=x-r-node.stroke_mm/2-left.points[2]-left.stroke_mm/2
            gap_right=right.points[0]-right.stroke_mm/2-x-r-node.stroke_mm/2
            if min(gap_left,gap_right)<.5-1e-9 or left.points[2]-left.points[0]<2*left.stroke_mm or right.points[2]-right.points[0]<2*right.stroke_mm:
                raise TechnicalMarkError("rule must retain node gaps and usable straight segments")
            for other in nodes:
                if abs(y-other.points[1])-r-other.points[2]-(node.stroke_mm+other.stroke_mm)/2<.35-1e-9:
                    raise TechnicalMarkError("rule nodes must retain clear lane separation")
            nodes.append(node)


def _geometry(value):
    if isinstance(value,TechnicalMark):
        _validate_stream(value)
        return value
    return technical_mark(value)


def _f(value):
    result=f"{value:.6f}".rstrip("0").rstrip(".")
    return "0" if result in {"","-0"} else result


def tikz_technical_mark(value) -> str:
    """Serialize the same native circles/lines, with no substrate-colored fill."""
    mark=_geometry(value)
    w,h=_f(mark.width_mm),_f(mark.height_mm)
    lines=[r"\begin{tikzpicture}[x=1mm,y=1mm,line cap=round]",
           rf"\path[use as bounding box] (0,0) rectangle ({w},{h});",
           rf"\clip (0,0) rectangle ({w},{h});"]
    for shape in mark.shapes:
        p=shape.points
        path=(f"({_f(p[0])},{_f(p[1])}) circle[radius={_f(p[2])}mm]" if shape.kind=="circle" else
              f"({_f(p[0])},{_f(p[1])}) -- ({_f(p[2])},{_f(p[3])})")
        lines.append(r"\path[fill=none,draw=BGInk,line width="+_f(shape.stroke_mm)+"mm] "+path+";")
    return "\n".join((*lines,r"\end{tikzpicture}"))+"\n"


def svg_technical_mark(value, palette: Mapping[str,str]) -> str:
    """Export transparent geometry in the family's explicit ink color."""
    mark=_geometry(value)
    if not isinstance(palette,Mapping) or set(palette)!={"ink","page","accent","line"} or any(not isinstance(v,str) or not _HEX.fullmatch(v) for v in palette.values()):
        raise TechnicalMarkError("palette requires explicit ink/page/accent/line hex colors")
    w,h=_f(mark.width_mm),_f(mark.height_mm)
    clip="technical-"+w.replace(".","p")+"-"+h.replace(".","p")
    lines=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}mm" height="{h}mm" viewBox="0 0 {w} {h}">',
           f'<defs><clipPath id="{clip}"><rect width="{w}" height="{h}"/></clipPath></defs>',
           f'<g clip-path="url(#{clip})"><g transform="translate(0 {h}) scale(1 -1)" fill="none" stroke={quoteattr(palette["ink"])} stroke-linecap="round">']
    for shape in mark.shapes:
        attrs=dict(zip(("cx","cy","r") if shape.kind=="circle" else ("x1","y1","x2","y2"),map(_f,shape.points)))
        attrs["stroke-width"]=_f(shape.stroke_mm)
        lines.append("<"+shape.kind+" "+" ".join(k+"="+quoteattr(v) for k,v in attrs.items())+"/>")
    return "\n".join((*lines,"</g></g>","</svg>"))+"\n"
