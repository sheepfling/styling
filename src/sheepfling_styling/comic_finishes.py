"""Bounded native slash knockouts and broken clipped keylines.

Scratch holes are true even-odd vector apertures, not page-colored overprints.
The helper contains no profile colors, font decisions, copy, or raster assets.
Coordinates are millimetres with positive y up, shared by both serializers.
"""
from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from xml.sax.saxutils import quoteattr


class FinishError(ValueError):
    """A finish recipe or native point stream violates its bounded grammar."""


@dataclass(frozen=True)
class FinishPrimitive:
    kind: str
    contours: tuple[tuple[tuple[float,float],...],...]
    stroke_mm: float
    fill: str | None = None
    stroke: str | None = None


@dataclass(frozen=True)
class ComicFinish:
    kind: str
    width_mm: float
    height_mm: float
    mode: str
    shapes: tuple[FinishPrimitive,...]

    @property
    def contour_count(self):return sum(len(shape.contours) for shape in self.shapes)


_COLORS={"ink":"BGInk","page":"BGPage","accent":"BGAccent","line":"BGLine"}
_HEX=re.compile(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\Z")
_DEFAULTS={"scratch-slashes":{"stroke_mm":.25,"count":4,"slant":.6,"strength":.45,"mode":"auto","cut_style":"bent"},
           "cut-keyline":{"stroke_mm":.25,"inset_mm":1.2,"cut_mm":2.,"break_mm":2.5,"echo":True}}


def _number(value:Any,name:str,low:float,high:float)->float:
    if isinstance(value,bool) or not isinstance(value,(int,float)):
        raise FinishError(f"{name} must be a finite number in {low}..{high}")
    try:result=float(value)
    except (ValueError,OverflowError) as exc:raise FinishError(f"{name} must be finite") from exc
    if not math.isfinite(result) or not low<=result<=high:raise FinishError(f"{name} must be a finite number in {low}..{high}")
    return result


def _bar(width,height,p):
    skew=p["slant"]*min(.7*height,.24*width)
    step=(.88*width-skew)/p["count"]
    return skew,step,.76*step


def validate_finish(recipe:Mapping[str,Any])->dict[str,Any]:
    """Normalize the closed physical recipe; auto mode resolves explicitly.

    Slashes support 2..7 bars, .2..85 slant, 0..1 strength, and
    auto/clean/scratched mode. Auto resolves to clean below 24 mm wide or
    10 mm high, and when the requested notch width would crowd the bars.
    Strength zero always resolves to clean. Up to three holes per bar use
    straight parallel edges or the legacy bent strip (the default).
    Keyline inset/cut/break limits preserve open edges.
    Every parameter is finite; no raw drawing code is accepted.
    """
    if not isinstance(recipe,Mapping) or set(recipe)-{"kind","width_mm","height_mm","parameters"}:
        raise FinishError("finish requires only kind, width_mm, height_mm, parameters")
    kind=recipe.get("kind")
    if not isinstance(kind,str) or kind not in _DEFAULTS:raise FinishError("unsupported finish kind")
    width=_number(recipe.get("width_mm"),"width_mm",8 if kind=="scratch-slashes" else 16,180)
    height=_number(recipe.get("height_mm"),"height_mm",6 if kind=="scratch-slashes" else 12,120)
    supplied=recipe.get("parameters",{})
    if not isinstance(supplied,Mapping) or set(supplied)-set(_DEFAULTS[kind]):raise FinishError("unsupported finish parameters")
    p={**_DEFAULTS[kind],**supplied};p["stroke_mm"]=_number(p["stroke_mm"],"stroke_mm",.15,1.2)
    if kind=="scratch-slashes":
        if isinstance(p["count"],bool) or not isinstance(p["count"],int) or not 2<=p["count"]<=7:raise FinishError("count must be an integer in 2..7")
        p["slant"]=_number(p["slant"],"slant",.2,.85);p["strength"]=_number(p["strength"],"strength",0,1)
        if not isinstance(p["mode"],str) or p["mode"] not in {"auto","clean","scratched"}:raise FinishError("mode must be auto, clean or scratched")
        if not isinstance(p["cut_style"],str) or p["cut_style"] not in {"straight","bent"}:raise FinishError("cut_style must be straight or bent")
        notch=max(.15,p["stroke_mm"]*(.6+.6*p["strength"]))
        feasible=width>=24 and height>=10 and _bar(width,height,p)[2]>=1.5*notch and .7*height>=6*notch
        if p["strength"]==0:p["mode"]="clean"
        elif p["mode"]=="auto":p["mode"]="scratched" if feasible else "clean"
        elif p["mode"]=="scratched" and not feasible:raise FinishError("scratched mode requires adequate physical bar and notch space; use clean at small sizes")
    else:
        p["inset_mm"]=_number(p["inset_mm"],"inset_mm",.6,6)
        p["cut_mm"]=_number(p["cut_mm"],"cut_mm",.5,8)
        p["break_mm"]=_number(p["break_mm"],"break_mm",0,8)
        if not isinstance(p["echo"],bool):raise FinishError("echo must be a boolean")
        inset,cut=p["inset_mm"],p["cut_mm"]
        if inset<p["stroke_mm"]/2+.15:raise FinishError("inset must contain the full stroke")
        if cut>.30*min(width-2*inset,height-2*inset):raise FinishError("cut and inset must leave an open frame")
        if p["break_mm"]>.4*(width-2*inset-cut):raise FinishError("break must retain both top rule segments")
    return {"kind":kind,"width_mm":width,"height_mm":height,"parameters":p}


def finish_geometry(recipe:Mapping[str,Any])->ComicFinish:
    """Create an immutable measured primitive stream, including true holes."""
    r=validate_finish(recipe);kind,w,h,p=(r[k] for k in ("kind","width_mm","height_mm","parameters"))
    shapes=[];stroke=p["stroke_mm"]
    def line(a,b,color="ink"):
        shapes.append(FinishPrimitive("line",((a,b),),stroke,stroke=color))
    if kind=="scratch-slashes":
        skew,step,bw=_bar(w,h,p);barheight=.7*h
        holes=0 if p["mode"]=="clean" else 1+min(2,int(p["strength"]*3))
        notch=max(.15,stroke*(.6+.6*p["strength"]))
        for index in range(p["count"]):
            x=.06*w+index*step;y=.15*h
            def physical(u,v):return (x+u+skew*v/barheight,y+v)
            contours=[tuple(physical(u,v) for u,v in ((0,0),(bw,0),(bw,barheight),(0,barheight)))]
            for scratch in range(holes):
                base=(.20+.22*scratch)*barheight
                # Straight cuts have no intermediate bend. Keep the old chain
                # as the default so earlier recipes retain their native paths.
                upper=(((.10*bw,base),(.90*bw,base+.09*barheight)) if p["cut_style"]=="straight" else
                       ((.10*bw,base),(.54*bw,base+.035*barheight),(.90*bw,base+.09*barheight)))
                # A monotone strip and its exact vertical offset cannot
                # cross, including large physical sizes with very fine wear.
                contours.append(tuple(physical(u,v) for u,v in (*upper,*((u,v+notch) for u,v in reversed(upper)))))
            shapes.append(FinishPrimitive("compound",tuple(contours),stroke,fill="accent"))
        mode=p["mode"]
    else:
        i,c,b=p["inset_mm"],p["cut_mm"],p["break_mm"]
        points=((i,i),(w-i-c,i),(w-i,i+c),(w-i,h-i),(i+c,h-i),(i,h-i-c))
        for index in (0,1,2,4,5):line(points[index],points[(index+1)%6])
        left,right=i+c,w-i;middle=(left+right)/2
        if b:
            line((right,h-i),(middle+b/2,h-i));line((middle-b/2,h-i),(left,h-i))
            line((middle-b*.35,h-i-1),(middle+b*.35,h-i-1),"accent")
        else:line((right,h-i),(left,h-i))
        if p["echo"]:
            offset=min(1.4,max(.65,.8*stroke))
            line((i+offset,h-i-c-offset),(i+c+offset,h-i-offset),"line")
            line((w-i-c-offset,i+offset),(w-i-offset,i+c+offset),"line")
        mode="keyline"
    result=ComicFinish(kind,w,h,mode,tuple(shapes));_validate_stream(result);return result


def _validate_stream(finish):
    if not isinstance(finish,ComicFinish) or not isinstance(finish.kind,str) or finish.kind not in _DEFAULTS:raise FinishError("export requires a ComicFinish or recipe")
    w=_number(finish.width_mm,"width_mm",8 if finish.kind=="scratch-slashes" else 16,180)
    h=_number(finish.height_mm,"height_mm",6 if finish.kind=="scratch-slashes" else 12,120)
    if not isinstance(finish.mode,str) or finish.mode not in {"clean","scratched","keyline"}:raise FinishError("invalid geometry mode")
    if (finish.kind=="cut-keyline")!=(finish.mode=="keyline"):raise FinishError("geometry mode differs from finish kind")
    if not isinstance(finish.shapes,tuple) or not 1<=len(finish.shapes)<=10:raise FinishError("primitive stream exceeds its bound")
    contours=points=0
    for shape in finish.shapes:
        if not isinstance(shape,FinishPrimitive) or not isinstance(shape.kind,str) or shape.kind not in {"line","compound"}:raise FinishError("unsupported primitive")
        _number(shape.stroke_mm,"stroke_mm",.15,1.2)
        if any(v is not None and (not isinstance(v,str) or v not in _COLORS) for v in (shape.fill,shape.stroke)):raise FinishError("colors must be semantic")
        if not isinstance(shape.contours,tuple) or not 1<=len(shape.contours)<=4:raise FinishError("invalid contour count")
        if shape.kind=="line" and (len(shape.contours)!=1 or len(shape.contours[0])!=2):raise FinishError("line needs exactly two endpoints")
        margin=shape.stroke_mm/2 if shape.stroke else 0
        for contour in shape.contours:
            if not isinstance(contour,tuple) or not (2 if shape.kind=="line" else 3)<=len(contour)<=6:raise FinishError("invalid contour points")
            for point in contour:
                if not isinstance(point,tuple) or len(point)!=2:raise FinishError("invalid coordinate pair")
                _number(point[0],"x",margin,w-margin);_number(point[1],"y",margin,h-margin)
            contours+=1;points+=len(contour)
        if shape.kind=="compound":
            for contour in shape.contours:_simple(contour)
            outer,*holes=shape.contours
            if finish.mode=="clean" and holes:raise FinishError("clean mode cannot contain scratch holes")
            for index,hole in enumerate(holes):
                if not all(_inside(outer,point) for point in hole) or _edges_touch(outer,hole):raise FinishError("scratch holes must remain strictly inside their bar")
                for other in holes[:index]:
                    if _edges_touch(hole,other) or _inside(hole,other[0]) or _inside(other,hole[0]):raise FinishError("scratch holes must not touch or overlap")
    if contours>28 or points>154:raise FinishError("geometry exceeds contour or point cap")


def _cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
def _on(a,b,p):return abs(_cross(a,b,p))<=1e-9 and min(a[0],b[0])-1e-9<=p[0]<=max(a[0],b[0])+1e-9 and min(a[1],b[1])-1e-9<=p[1]<=max(a[1],b[1])+1e-9
def _touch(a,b,c,d):
    ac,ad,ca,cb=_cross(a,b,c),_cross(a,b,d),_cross(c,d,a),_cross(c,d,b)
    return (ac*ad<0 and ca*cb<0) or any((_on(a,b,c),_on(a,b,d),_on(c,d,a),_on(c,d,b)))
def _edges(poly):return tuple(zip(poly,poly[1:]+poly[:1]))
def _edges_touch(first,second):return any(_touch(a,b,c,d) for a,b in _edges(first) for c,d in _edges(second))
def _inside(poly,p):
    inside=False
    for a,b in _edges(poly):
        if _on(a,b,p):return False
        if (a[1]>p[1])!=(b[1]>p[1]) and p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]:inside=not inside
    return inside
def _simple(poly):
    edges=_edges(poly)
    if any(a==b for a,b in edges) or abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in edges))<1e-9:raise FinishError("contours need nonzero area and edges")
    for i,(a,b) in enumerate(edges):
        for j,(c,d) in enumerate(edges[i+1:],i+1):
            if j==i+1 or i==0 and j==len(edges)-1:continue
            if _touch(a,b,c,d):raise FinishError("contours must be simple, without self-intersection")


def _geometry(value):
    if isinstance(value,ComicFinish):_validate_stream(value);return value
    return finish_geometry(value)


def _f(value):
    result=f"{value:.6f}".rstrip("0").rstrip(".");return "0" if result in {"","-0"} else result


def tikz_finish(value)->str:
    """Serialize recipe or immutable geometry as one clipped native picture."""
    finish=_geometry(value);w,h=_f(finish.width_mm),_f(finish.height_mm)
    lines=[r"\begin{tikzpicture}[x=1mm,y=1mm,line cap=round,line join=round]",rf"\path[use as bounding box] (0,0) rectangle ({w},{h});",rf"\clip (0,0) rectangle ({w},{h});"]
    for shape in finish.shapes:
        options=["fill="+(_COLORS[shape.fill] if shape.fill else "none"),"draw="+(_COLORS[shape.stroke] if shape.stroke else "none")]
        if shape.stroke:options.append("line width="+_f(shape.stroke_mm)+"mm")
        if shape.kind=="compound":options.append("even odd rule")
        paths=[" -- ".join(f"({_f(x)},{_f(y)})" for x,y in contour)+(" -- cycle" if shape.kind=="compound" else "") for contour in shape.contours]
        lines.append(r"\path["+",".join(options)+"] "+" ".join(paths)+";")
    lines.append(r"\end{tikzpicture}");return "\n".join(lines)+"\n"


def svg_finish(value,palette:Mapping[str,str])->str:
    """Serialize true transparent compound holes, with explicit profile colors."""
    finish=_geometry(value)
    if not isinstance(palette,Mapping) or set(palette)!=set(_COLORS) or any(not isinstance(v,str) or not _HEX.fullmatch(v) for v in palette.values()):raise FinishError("palette requires ink/page/accent/line hex colors")
    w,h=_f(finish.width_mm),_f(finish.height_mm);clip="finish-"+w.replace(".","p")+"-"+h.replace(".","p")
    lines=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}mm" height="{h}mm" viewBox="0 0 {w} {h}">',f'<defs><clipPath id="{clip}"><rect width="{w}" height="{h}"/></clipPath></defs>',f'<g clip-path="url(#{clip})"><g transform="translate(0 {h}) scale(1 -1)" stroke-linecap="round" stroke-linejoin="round">']
    for shape in finish.shapes:
        attrs={"fill":palette[shape.fill] if shape.fill else "none","stroke":palette[shape.stroke] if shape.stroke else "none"}
        if shape.stroke:attrs["stroke-width"]=_f(shape.stroke_mm)
        if shape.kind=="compound":attrs["fill-rule"]="evenodd"
        attrs["d"]=" ".join("M "+" L ".join(f"{_f(x)} {_f(y)}" for x,y in contour)+(" Z" if shape.kind=="compound" else "") for contour in shape.contours)
        lines.append("<path "+" ".join(k+"="+quoteattr(v) for k,v in attrs.items())+"/>")
    lines.extend(("</g></g>","</svg>"));return "\n".join(lines)+"\n"
