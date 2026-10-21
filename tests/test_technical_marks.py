"""Physical separation, transparency and native backend parity for technical marks."""
import copy
import dataclasses
import math
from pathlib import Path
import re
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from sheepfling_styling.technical_marks import (
    TechnicalMarkError,technical_mark,validate_technical_mark,tikz_technical_mark,svg_technical_mark,
)

PALETTE={"ink":"#123456","page":"#FC37A5","accent":"#FA4800","line":"#333333"}
NS={"s":"http://www.w3.org/2000/svg"}
def recipe(kind="concentric-rings",w=24,h=24,**p):
    return {"kind":kind,"width_mm":w,"height_mm":h,"parameters":p}


class TechnicalMarkTests(unittest.TestCase):
    def test_normalization_is_fresh_idempotent_and_geometry_is_immutable(self):
        r=recipe();before=copy.deepcopy(r);v=validate_technical_mark(r)
        self.assertEqual(r,before);self.assertEqual(validate_technical_mark(v),v)
        g=technical_mark(r);self.assertEqual(g,technical_mark(r))
        with self.assertRaises(dataclasses.FrozenInstanceError):g.width_mm=99

    def test_rings_share_one_center_and_retain_measured_air(self):
        for size,n,s in ((8,5,.25),(12,7,.25),(160,8,1.2)):
            height=min(160,size+3)
            g=technical_mark(recipe(w=size,h=height,rings=n,stroke_mm=s))
            self.assertEqual(len(g.shapes),n)
            self.assertEqual({item.points[:2] for item in g.shapes},{(size/2,height/2)})
            radii=[item.points[2] for item in g.shapes]
            self.assertGreater(radii[0]-s/2,0)
            self.assertTrue(all(b-a-s>=.2-1e-9 for a,b in zip(radii,radii[1:])))
            self.assertLessEqual(radii[-1]+s/2,size/2)

    def test_rule_gaps_include_round_caps_and_hollow_circle_stroke(self):
        for lanes in (1,2,3):
            g=technical_mark(recipe("signal-rule",60,18,lanes=lanes,gap_mm=2,node_radius_mm=1))
            centers=[]
            for a,c,b in zip(g.shapes[::3],g.shapes[1::3],g.shapes[2::3]):
                x,y,r=c.points;s=c.stroke_mm
                self.assertAlmostEqual((x-r-s/2)-(a.points[2]+s/2),2)
                self.assertAlmostEqual((b.points[0]-s/2)-(x+r+s/2),2)
                self.assertEqual(a.points[1],y);self.assertEqual(b.points[1],y)
                centers.append(x)
            self.assertEqual(centers,[45,15,45][:lanes])

    def test_serializers_share_coordinates_and_preserve_transparent_centers(self):
        for r in (recipe(w=8,h=8),recipe(w=160,h=160,rings=8),
                  recipe("signal-rule",20,6,lanes=1,node_radius_mm=.6,gap_mm=.5),
                  recipe("signal-rule",180,48,stroke_mm=1.2,node_radius_mm=2.5,gap_mm=6)):
            g=technical_mark(r);svg=svg_technical_mark(g,PALETTE);tikz=tikz_technical_mark(g)
            nodes=ET.fromstring(svg).findall(".//s:circle",NS)+ET.fromstring(svg).findall(".//s:line",NS)
            self.assertEqual(len(nodes),len(g.shapes))
            svg_order=list(ET.fromstring(svg).find("s:g/s:g",NS))
            tikz_records=tikz.split(r"\path[")[2:]
            for shape,node,record in zip(g.shapes,svg_order,tikz_records,strict=True):
                keys=("cx","cy","r") if shape.kind=="circle" else ("x1","y1","x2","y2")
                self.assertEqual([round(x,6) for x in shape.points],[float(node.get(k)) for k in keys])
                points=[float(v) for pair in re.findall(r"\(([-\d.]+),([-\d.]+)\)",record) for v in pair]
                if shape.kind=="circle":points.append(float(re.search(r"radius=([-\d.]+)mm",record).group(1)))
                self.assertEqual(points,[float(node.get(k)) for k in keys])
            self.assertIn('fill="none"',svg);self.assertNotIn(PALETTE['page'],svg)
            self.assertNotIn('BGPage',tikz);self.assertNotIn('<image',svg)
            self.assertEqual(tikz,tikz_technical_mark(r));self.assertEqual(svg,svg_technical_mark(r,PALETTE))

    def test_collapsed_gaps_and_unknown_nonfinite_parameters_reject(self):
        bad=[[],{},recipe(w=True),recipe(h=math.inf),recipe(rings=True),recipe(rings=9),recipe(w=8,h=8,rings=8),
             recipe(stroke_mm=.14),recipe(inner_ratio=[]),recipe(raw_tex='x'),recipe("signal-rule",20,6),
             recipe("signal-rule",20,6,lanes=1,gap_mm=6),recipe("signal-rule",60,12,lanes=3,node_radius_mm=2.5),
             recipe("signal-rule",60,12,lanes=0),recipe("signal-rule",60,12,gap_mm=math.nan)]
        for r in bad:
            with self.subTest(r=r),self.assertRaises(TechnicalMarkError):technical_mark(r)

    def test_exports_recheck_forged_stream_and_palette(self):
        g=technical_mark(recipe());s=g.shapes[0]
        for forged in (dataclasses.replace(g,shapes=[]),dataclasses.replace(g,shapes=(dataclasses.replace(s,points=(0,0,2)),)),
                       dataclasses.replace(g,shapes=(dataclasses.replace(s,kind=[]),)),dataclasses.replace(g,shapes=g.shapes*3)):
            with self.assertRaises(TechnicalMarkError):tikz_technical_mark(forged)
        for palette in ({},{**PALETTE,'ink':'url(x)'},{**PALETTE,'page':None}):
            with self.assertRaises(TechnicalMarkError):svg_technical_mark(g,palette)
        with self.assertRaises(TechnicalMarkError):
            tikz_technical_mark(dataclasses.replace(g,shapes=(s,)*5))
        rule=technical_mark(recipe("signal-rule",60,18));left,node,right,*tail=rule.shapes
        for forged in (dataclasses.replace(rule,shapes=(left,dataclasses.replace(node,points=(left.points[2],node.points[1],.8)),right,*tail)),
                       dataclasses.replace(rule,shapes=rule.shapes[:3]*2)):
            with self.assertRaises(TechnicalMarkError):svg_technical_mark(forged,PALETTE)


if __name__=="__main__":unittest.main()
