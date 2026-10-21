"""Finish bounds, true knockout topology, and native serializer agreement."""
import copy
import dataclasses
import math
from pathlib import Path
import re
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from sheepfling_styling.comic_finishes import FinishError,finish_geometry,validate_finish,tikz_finish,svg_finish

PALETTE={"ink":"#090C0A","page":"#C43963","accent":"#65FF00","line":"#748078"}
NS={"s":"http://www.w3.org/2000/svg"}
def recipe(kind="scratch-slashes",w=60,h=30,**p):return {"kind":kind,"width_mm":w,"height_mm":h,"parameters":p}


class ComicFinishesTests(unittest.TestCase):
    def test_normalization_is_fresh_deterministic_and_immutable(self):
        r=recipe();before=copy.deepcopy(r);v=validate_finish(r)
        self.assertEqual(r,before);self.assertEqual(validate_finish(v),v)
        mark=finish_geometry(r);self.assertEqual(mark,finish_geometry(r))
        with self.assertRaises(dataclasses.FrozenInstanceError):mark.mode="clean"
        self.assertEqual(tikz_finish(r),tikz_finish(mark))

    def test_small_auto_and_zero_strength_are_explicitly_clean(self):
        for r in (recipe(w=12,h=6),recipe(w=60,h=30,strength=0,mode="scratched"),recipe(w=24,h=10,count=7,stroke_mm=1.2,strength=1)):
            v=validate_finish(r);g=finish_geometry(r)
            self.assertEqual(v["parameters"]["mode"],"clean")
            self.assertEqual(g.contour_count,len(g.shapes))
        with self.assertRaises(FinishError):finish_geometry(recipe(w=12,h=6,mode="scratched"))

    def test_large_thin_scratch_regression_is_simple_and_strictly_contained(self):
        for stroke in (.15,.25,.35,.5,1.2):
            for count in (2,4,7):
                for strength in (.1,.45,1):
                    g=finish_geometry(recipe(w=180,h=120,stroke_mm=stroke,count=count,strength=strength))
                    self.assertEqual(g.mode,"scratched")
                    for shape in g.shapes:
                        a,b,_,d=shape.contours[0];ux,uy=b[0]-a[0],b[1]-a[1];vx,vy=d[0]-a[0],d[1]-a[1];det=ux*vy-uy*vx
                        for hole in shape.contours[1:]:
                            # Inverse affine coordinates independently prove
                            # every notch stays strictly within its own slab.
                            for x,y in hole:
                                u=((x-a[0])*vy-(y-a[1])*vx)/det;v=(ux*(y-a[1])-uy*(x-a[0]))/det
                                self.assertTrue(0<u<1 and 0<v<1)
                            # The lower chain is the exact offset of the upper
                            # chain in reverse; both graphs are monotone in x.
                            upper,lower=hole[:3],tuple(reversed(hole[3:]))
                            offsets=[(round(q[0]-p[0],8),round(q[1]-p[1],8)) for p,q in zip(upper,lower)]
                            self.assertEqual(len(set(offsets)),1)
                            self.assertGreater(offsets[0][1],0)

    def test_true_holes_do_not_paint_the_supplied_page_color(self):
        r=recipe(strength=1);svg=svg_finish(r,PALETTE);tikz=tikz_finish(r)
        nodes=ET.fromstring(svg).findall(".//s:path",NS)
        self.assertTrue(all(node.get("fill-rule")=="evenodd" for node in nodes))
        self.assertEqual(sum(node.get("d").count("M ") for node in nodes),finish_geometry(r).contour_count)
        self.assertNotIn(PALETTE["page"],svg);self.assertNotIn("BGPage",tikz)
        self.assertEqual(tikz.count("even odd rule"),len(nodes))

    def test_straight_cuts_have_parallel_edges_and_no_bend(self):
        for w,h in ((29,30),(38,40),(180,120)):
            for count in (2,4,7):
                for strength in (.15,.45,1):
                    r=recipe(w=w,h=h,count=count,strength=strength,cut_style="straight")
                    g=finish_geometry(r)
                    for shape in g.shapes:
                        a,b,_,d=shape.contours[0]
                        det=(b[0]-a[0])*(d[1]-a[1])-(b[1]-a[1])*(d[0]-a[0])
                        for hole in shape.contours[1:]:
                            self.assertEqual(len(hole),4)
                            p,q,r,s=hole
                            self.assertAlmostEqual(q[0]-p[0],r[0]-s[0])
                            self.assertAlmostEqual(q[1]-p[1],r[1]-s[1])
                            for x,y in hole:
                                u=((x-a[0])*(d[1]-a[1])-(y-a[1])*(d[0]-a[0]))/det
                                v=((b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0]))/det
                                self.assertTrue(0<u<1 and 0<v<1)
                    self.assertIn('fill-rule="evenodd"',svg_finish(g,PALETTE))
                    self.assertNotIn(PALETTE["page"],svg_finish(g,PALETTE))

    def test_legacy_bent_default_is_explicit_and_straight_style_is_validated(self):
        self.assertEqual(tikz_finish(recipe()),tikz_finish(recipe(cut_style="bent")))
        self.assertEqual(svg_finish(recipe(),PALETTE),svg_finish(recipe(cut_style="bent"),PALETTE))
        self.assertTrue(all(len(c)==6 for s in finish_geometry(recipe()).shapes for c in s.contours[1:]))
        for value in (None,[],True,"curved","Straight"):
            with self.subTest(value=value),self.assertRaises(FinishError):finish_geometry(recipe(cut_style=value))

    def test_backend_geometry_and_counts_match_at_extreme_physical_sizes(self):
        cases=[recipe(w=8,h=6,count=7,slant=.85),recipe(w=24,h=10,count=7),recipe(w=180,h=120,count=7,strength=1),
               recipe("cut-keyline",w=16,h=12,stroke_mm=1.2,inset_mm=.8,cut_mm=.5,break_mm=0,echo=False),
               recipe("cut-keyline",w=180,h=120,stroke_mm=1.2,inset_mm=6,cut_mm=8,break_mm=8)]
        for r in cases:
            with self.subTest(r=r):
                g=finish_geometry(r);svg,tikz=svg_finish(g,PALETTE),tikz_finish(g)
                nodes=ET.fromstring(svg).findall(".//s:path",NS)
                self.assertLessEqual(len(g.shapes),10);self.assertLessEqual(g.contour_count,28)
                self.assertLessEqual(sum(len(c) for s in g.shapes for c in s.contours),154)
                self.assertEqual(len(nodes),len(g.shapes))
                records=tikz.split("\\path[")[2:]
                self.assertEqual(len(records),len(nodes))
                for s,node,record in zip(g.shapes,nodes,records,strict=True):
                    svgnumbers=[float(v) for v in re.findall(r"-?\d+(?:\.\d+)?",node.get("d"))]
                    tikznumbers=[float(v) for pair in re.findall(r"\(([-\d.]+),([-\d.]+)\)",record) for v in pair]
                    self.assertEqual(svgnumbers,tikznumbers)
                    margin=s.stroke_mm/2 if s.stroke else 0
                    for c in s.contours:
                        for x,y in c:self.assertTrue(margin<=x<=g.width_mm-margin and margin<=y<=g.height_mm-margin)
                self.assertEqual(svg,svg_finish(r,PALETTE));self.assertNotIn("<image",svg);self.assertNotIn("<text",svg)

    def test_unknown_nonfinite_and_collapsed_parameters_reject(self):
        invalid=[[],{},recipe(w=True),recipe(w=math.nan),recipe(h=math.inf),recipe(w=181),recipe(count=True),recipe(count=4.),
                 recipe(count=8),recipe(slant=.9),recipe(strength=-.1),recipe(stroke_mm=.14),recipe(mode=[]),recipe(raw_tex="x"),
                 recipe("cut-keyline",w=15),recipe("cut-keyline",inset_mm=.6,stroke_mm=1.2),recipe("cut-keyline",w=16,h=12,inset_mm=6),
                 recipe("cut-keyline",w=16,h=12,cut_mm=8),recipe("cut-keyline",w=16,h=12,break_mm=8),recipe("cut-keyline",echo=1)]
        for r in invalid:
            with self.subTest(r=r),self.assertRaises(FinishError):finish_geometry(r)
        for p in ({},{**PALETTE,"ink":"url(x)"},{**PALETTE,"page":'red"/><image/>'}):
            with self.assertRaises(FinishError):svg_finish(recipe(),p)

    def test_forged_overflow_crossed_or_overlapping_holes_reject(self):
        g=finish_geometry(recipe());s=g.shapes[0];outer,hole,*_=s.contours
        bad=[dataclasses.replace(g,shapes=(dataclasses.replace(s,contours=(((0,0),(60,0),(60,30),(0,30)),((1,1),(3,3),(1,3),(3,1)))),)),
             dataclasses.replace(g,shapes=(dataclasses.replace(s,contours=(outer,hole,hole)),)),
             dataclasses.replace(g,shapes=(dataclasses.replace(s,contours=(outer,((0,0),(2,0),(2,2)))),)),
             dataclasses.replace(g,shapes=(dataclasses.replace(s,fill=[]),))]
        for field in bad:
            with self.assertRaises(FinishError):tikz_finish(field)
        k=finish_geometry(recipe("cut-keyline"));s=k.shapes[0]
        with self.assertRaises(FinishError):svg_finish(dataclasses.replace(k,shapes=(dataclasses.replace(s,contours=(((0,0),(10,0)),)),)),PALETTE)


if __name__=="__main__":unittest.main()
