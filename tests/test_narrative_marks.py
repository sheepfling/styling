"""Native narrative marks retain bounds, clear nodes, and backend parity."""
import copy
import dataclasses
import math
from pathlib import Path
import re
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from sheepfling_styling.narrative_marks import NarrativeMarkError,narrative_mark,validate_narrative_mark,svg_narrative_mark,tikz_narrative_mark

PALETTE={"ink":"#090C0A","page":"#F7F8F1","accent":"#65FF00","line":"#78847A"}
NS={"s":"http://www.w3.org/2000/svg"}


def recipe(kind="trajectory-fan",width=60,height=40,**parameters):
    return {"kind":kind,"width_mm":width,"height_mm":height,"parameters":parameters}


class NarrativeMarksTests(unittest.TestCase):
    def test_defaults_are_fresh_and_input_is_not_mutated(self):
        data=recipe(arms=5); before=copy.deepcopy(data)
        normalized=validate_narrative_mark(data)
        self.assertEqual(before,data)
        self.assertEqual(validate_narrative_mark(normalized),normalized)
        self.assertEqual(narrative_mark(data),narrative_mark(data))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            narrative_mark(data).width_mm=20

    def test_each_arm_is_tangent_to_its_hollow_terminal_and_has_distinct_anchor(self):
        for count in (3,4,5):
            mark=narrative_mark(recipe(arms=count))
            starts=[]
            for index in range(count):
                curve,node,start=mark.shapes[index*3:index*3+3]
                x,y,r=node.points
                self.assertEqual(curve.points[-2:],(x-r,y))
                self.assertEqual(curve.points[-3],y)
                self.assertEqual(node.fill,"page")
                self.assertEqual(node.stroke,"ink")
                self.assertEqual(start.points[:2],curve.points[:2])
                self.assertGreater(mark.label_anchors[index].x_mm,x+r)
                starts.append(curve.points[:2])
            self.assertEqual(len(set(starts)),count)
            nodes=[s for s in mark.shapes if s.kind=="circle" and s.stroke]
            for a,b in zip(nodes,nodes[1:]):
                self.assertGreater(math.dist(a.points[:2],b.points[:2]),a.points[2]+b.points[2]+a.stroke_mm)

    def test_curves_and_strokes_stay_in_measured_bounds_at_proof_scales(self):
        for kind in ("trajectory-fan","registration-tab"):
            for width,height in ((16,16),(24,20),(36,24),(60,30),(180,120)):
                with self.subTest(kind=kind,size=(width,height)):
                    mark=narrative_mark(recipe(kind,width,height))
                    for shape in mark.shapes:
                        self.assertGreaterEqual(shape.stroke_mm,.25)
                        if shape.kind=="circle":
                            x,y,r=shape.points; edge=shape.stroke_mm/2 if shape.stroke else 0
                            self.assertGreaterEqual(min(x-r-edge,y-r-edge),0)
                            self.assertLessEqual(x+r+edge,width)
                            self.assertLessEqual(y+r+edge,height)
                        else:
                            self.assertTrue(all(shape.stroke_mm/2 <= x <= width-shape.stroke_mm/2 for x in shape.points[::2]))
                            self.assertTrue(all(shape.stroke_mm/2 <= y <= height-shape.stroke_mm/2 for y in shape.points[1::2]))

    def test_serialized_native_geometry_matches_and_contains_no_copy_or_assets(self):
        for kind in ("trajectory-fan","registration-tab"):
            mark=narrative_mark(recipe(kind))
            svg,tikz=svg_narrative_mark(mark,PALETTE),tikz_narrative_mark(mark)
            self.assertEqual(svg,svg_narrative_mark(mark,PALETTE))
            nodes=list(ET.fromstring(svg).find("s:g/s:g",NS))
            records=tikz.split("% narrative primitive ")[1:]
            self.assertEqual(len(nodes),len(mark.shapes))
            self.assertEqual(len(records),len(nodes))
            for shape,node,record in zip(mark.shapes,nodes,records,strict=True):
                if shape.kind=="circle":
                    values=tuple(float(node.get(k)) for k in ("cx","cy","r"))
                    match=re.search(r"\(([-\d.]+),([-\d.]+)\) circle\[radius=([-\d.]+)mm\]",record)
                    self.assertEqual(values,tuple(map(float,match.groups())))
                else:
                    numbers=[float(v) for v in re.findall(r"[-\d.]+",node.get("d") or node.get("points") or " ".join(node.get(k) for k in ("x1","y1","x2","y2")))]
                    emitted=[float(v) for pair in re.findall(r"\(([-\d.]+),([-\d.]+)\)",record) for v in pair]
                    self.assertEqual(numbers,emitted)
            self.assertNotIn("<image",svg);self.assertNotIn("<text",svg);self.assertNotIn("includegraphics",tikz)
            self.assertEqual(ET.fromstring(svg).get("viewBox"),"0 0 60 40")

    def test_malformed_nonfinite_unknown_and_overlapping_nodes_reject(self):
        invalid=[{},[],recipe("bad"),recipe(width=math.nan),recipe(height=math.inf),recipe(width=True),recipe(width=181),
                 recipe(stroke_mm=.24),recipe(stroke_mm=2),recipe(arms=True),recipe(arms=4.),recipe(arms=6),
                 recipe(node_radius_mm=math.nan),recipe(width=16,height=16,arms=5,node_radius_mm=1.2,stroke_mm=.25),
                 recipe(raw_tikz="payload"),recipe("registration-tab",width=16,cut_mm=5),
                 recipe("registration-tab",width=16,rail_width_mm=8),recipe("registration-tab",registration_radius_mm=2,stroke_mm=1),
                 {**recipe(),"text":"identity"}]
        for value in invalid:
            with self.subTest(value=value),self.assertRaises(NarrativeMarkError):
                narrative_mark(value)

    def test_palette_and_hand_built_exports_cannot_inject_code(self):
        mark=narrative_mark(recipe())
        for palette in ({},{**PALETTE,"ink":"red"},{**PALETTE,"ink":'#fff"/><image/>'}):
            with self.assertRaises(NarrativeMarkError):svg_narrative_mark(mark,palette)
        bad=dataclasses.replace(mark,shapes=(dataclasses.replace(mark.shapes[0],points=(0,0,1,1,2,2,math.nan,3)),))
        with self.assertRaises(NarrativeMarkError):tikz_narrative_mark(bad)
        for bad in (dataclasses.replace(mark,kind=[]),
                    dataclasses.replace(mark,shapes=(dataclasses.replace(mark.shapes[0],kind=[]),)),
                    dataclasses.replace(mark,shapes=(dataclasses.replace(mark.shapes[0],stroke=[]),)),
                    dataclasses.replace(mark,label_anchors=(dataclasses.replace(mark.label_anchors[0],alignment=[]),))):
            with self.subTest(bad=bad),self.assertRaises(NarrativeMarkError):tikz_narrative_mark(bad)

    def test_large_stroke_terminal_overflow_rejects_and_exact_boundary_is_allowed(self):
        with self.assertRaisesRegex(NarrativeMarkError,"including stroke"):
            narrative_mark(recipe(width=16,height=16,arms=3,node_radius_mm=1.8,stroke_mm=1.5))
        allowed=narrative_mark(recipe(width=16,height=16,arms=3,node_radius_mm=1.65,stroke_mm=1.5))
        self.assertAlmostEqual(allowed.shapes[1].points[1]+allowed.shapes[1].points[2]+.75,16)
        tikz_narrative_mark(allowed)
        forged=dataclasses.replace(allowed,shapes=(dataclasses.replace(allowed.shapes[1],points=(12,14,1.8)),))
        with self.assertRaises(NarrativeMarkError):svg_narrative_mark(forged,PALETTE)
        forged=dataclasses.replace(allowed,label_anchors=(dataclasses.replace(allowed.label_anchors[0],x_mm=math.nan),))
        with self.assertRaises(NarrativeMarkError):tikz_narrative_mark(forged)


if __name__=="__main__":unittest.main()
