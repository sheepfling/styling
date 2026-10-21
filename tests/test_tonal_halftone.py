"""Tonal dots preserve measured area, coverage, orientation, and backend parity."""
from __future__ import annotations

import dataclasses
import math
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sheepfling_styling.tonal_halftone import (  # noqa: E402
    MAX_SAMPLES, TonalHalftoneError,
    corner_halftone, svg_tonal_halftone, tikz_tonal_halftone, tonal_halftone,
)

NS = {"svg": "http://www.w3.org/2000/svg"}


def field(tones, **knobs):
    return tonal_halftone(tones, width_mm=40, height_mm=30, **knobs)


class TonalHalftoneTests(unittest.TestCase):
    def test_corner_dissolves_mirror_and_scale_in_both_axes(self):
        fields={c:corner_halftone(width_mm=44,height_mm=44,corner=c) for c in
                ("top-left","top-right","bottom-left","bottom-right")}
        pointset=lambda f:{tuple(round(v,8) for v in circle) for circle in f.circles}
        original=fields["bottom-right"]
        self.assertEqual(pointset(fields["bottom-left"]),{(round(44-x,8),round(y,8),round(r,8)) for x,y,r in original.circles})
        self.assertEqual(pointset(fields["top-right"]),{(round(x,8),round(44-y,8),round(r,8)) for x,y,r in original.circles})
        dots={(round(x,8),round(y,8)):r for x,y,r in original.circles}
        self.assertGreater(dots[(43.3125,.6875)],dots[(32.3125,.6875)])
        self.assertGreater(dots[(43.3125,.6875)],dots[(43.3125,11.6875)])
        self.assertNotIn((.6875,43.3125),dots)
        for f in fields.values():
            self.assertEqual(f.sample_count,1024)
            self.assertLess(f.circle_count,f.sample_count)
            self.assertEqual(svg_tonal_halftone(f,"#000").count("<circle"),f.circle_count)
            self.assertEqual(tikz_tonal_halftone(f).count("circle [radius="),f.circle_count)
            self.assertTrue(all(r<=.46*44/32 for x,y,r in f.circles))

    def test_corner_grid_rejects_unknown_orientation_and_unbounded_inputs(self):
        for knobs in ({"corner":"right"},{"corner":[]},{"rows":True},{"columns":65},
                      {"columns":64,"rows":64},{"fade_radius_ratio":math.nan},{"fade_radius_ratio":.1}):
            with self.subTest(knobs=knobs),self.assertRaises(TonalHalftoneError):
                corner_halftone(**{"width_mm":44,"height_mm":44,"corner":"bottom-right",**knobs})

    def test_darkness_maps_to_ink_area_not_diameter(self):
        result = field([[0, 0.5, 0.75, 1]], dot_min_mm=0, dot_max_mm=1)
        self.assertEqual(result.sample_count, 4)
        self.assertEqual(result.circle_count, 3)
        areas_without_pi = [circle[2] ** 2 for circle in result.circles]
        for measured, expected in zip(areas_without_pi, [1, 0.5, 0.25], strict=True):
            self.assertAlmostEqual(measured, expected)

    def test_coverage_scales_actual_ink_area_and_transparency_emits_no_circle(self):
        result = field([[0.3] * 4], coverage=[[1, 0.5, 0.25, 0]])
        self.assertEqual(result.circle_count, 3)
        areas = [circle[2] ** 2 for circle in result.circles]
        self.assertAlmostEqual(areas[1] / areas[0], 0.5)
        self.assertAlmostEqual(areas[2] / areas[0], 0.25)
        self.assertEqual(field([[0]], coverage=[[0]]).circles, ())
        self.assertEqual(field([[1]], coverage=[[1]]).circles, ())

    def test_floor_radius_is_included_before_coverage_and_white_stays_empty(self):
        result = field([[0.5, 1]], dot_min_mm=.2, dot_max_mm=.6, coverage=[[.25, 1]])
        self.assertEqual(result.circle_count, 1)
        self.assertAlmostEqual(result.circles[0][2] ** 2, .25 * (.2 ** 2 + (.6 ** 2 - .2 ** 2) * .5))

    def test_gamma_and_invert_control_density_without_affecting_placement(self):
        regular = field([[0.25, 1]], dot_min_mm=0, dot_max_mm=1)
        gamma_two = field([[0.25, 1]], dot_min_mm=0, dot_max_mm=1, gamma=2)
        inverted = field([[0.25, 1]], dot_min_mm=0, dot_max_mm=1, invert=True)
        self.assertEqual(regular.circles[0][:2], gamma_two.circles[0][:2])
        self.assertAlmostEqual(gamma_two.circles[0][2] ** 2, .75 ** 2)
        self.assertAlmostEqual(inverted.circles[0][2] ** 2, .25)
        self.assertEqual(inverted.circle_count, 2)

    def test_source_rows_map_from_top_down_to_y_up(self):
        result = tonal_halftone([[0, 1], [1, 0]], width_mm=12, height_mm=8)
        self.assertEqual([circle[:2] for circle in result.circles], [(3, 6), (9, 2)])
        svg = ET.fromstring(svg_tonal_halftone(result, "#123456"))
        inner = svg.find("svg:g/svg:g", NS)
        self.assertEqual(inner.get("transform"), "translate(0 8) scale(1 -1)")

    def test_radius_cap_preserves_contrast_and_keeps_every_dot_inside_cell(self):
        result = tonal_halftone([[0, .5] * 20] * 30, width_mm=10, height_mm=7,
                                dot_min_mm=.2, dot_max_mm=2)
        self.assertEqual(result.sample_count, MAX_SAMPLES)
        cap = .46 * min(10 / 40, 7 / 30)
        self.assertAlmostEqual(result.circles[0][2], cap)
        self.assertLess(result.circles[1][2], cap)
        self.assertAlmostEqual(result.circles[1][2] ** 2 / cap ** 2, .1 ** 2 + (1 - .1 ** 2) * .5)
        for x, y, radius in result.circles:
            self.assertGreaterEqual(x - radius, 0)
            self.assertGreaterEqual(y - radius, 0)
            self.assertLessEqual(x + radius, result.width_mm)
            self.assertLessEqual(y + radius, result.height_mm)

    def test_pointstream_and_exports_are_deterministic_native_geometry(self):
        data = [[0, .2, .5], [.75, .9, 1]]
        first, second = field(data), field(data)
        self.assertEqual(first, second)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            first.width_mm = 20
        self.assertEqual(svg_tonal_halftone(first, "#000"), svg_tonal_halftone(second, "#000"))
        self.assertEqual(tikz_tonal_halftone(first), tikz_tonal_halftone(second))
        svg = svg_tonal_halftone(first, "#000")
        tikz = tikz_tonal_halftone(first)
        self.assertNotIn("<image", svg)
        self.assertNotIn("<text", svg)
        self.assertNotIn("includegraphics", tikz)
        self.assertNotIn("foreach", tikz)
        self.assertEqual(tikz.count(r"\path[fill=BGInk,draw=none]"), 1)

    def test_native_serializers_have_identical_circle_counts_and_coordinates(self):
        for width, height in [(1, 1), (30, 20), (120, 70), (500, 1), (1, 500)]:
            with self.subTest(width=width, height=height):
                result = tonal_halftone([[0, .2, 1], [.5, .75, 0]], width_mm=width, height_mm=height,
                                        coverage=[[1, .25, .5], [.1, 1, 0]])
                svg = ET.fromstring(svg_tonal_halftone(result, "#010203"))
                nodes = svg.findall(".//svg:circle", NS)
                tikz = tikz_tonal_halftone(result)
                triples = re.findall(r"\(([-\d.]+),([-\d.]+)\) circle \[radius=([-\d.]+)mm\]", tikz)
                self.assertEqual(len(nodes), result.circle_count)
                self.assertEqual(len(nodes), len(triples))
                for node, triple in zip(nodes, triples, strict=True):
                    self.assertEqual(tuple(node.get(key) for key in ("cx", "cy", "r")), triple)
                self.assertEqual(svg.get("viewBox"), f"0 0 {width} {height}")

    def test_empty_field_still_has_fixed_bounding_box_and_valid_exports(self):
        result = field([[1, 1]], coverage=[[0, 1]])
        self.assertEqual(result.circles, ())
        svg = ET.fromstring(svg_tonal_halftone(result, "#fff"))
        self.assertEqual(svg.findall(".//svg:circle", NS), [])
        tikz = tikz_tonal_halftone(result)
        self.assertIn("rectangle (40,30)", tikz)
        self.assertNotIn("circle [radius", tikz)

    def test_subprecision_coverage_cannot_create_zero_radius_export_objects(self):
        result = field([[0, 0]], coverage=[[1e-50, 1]])
        self.assertEqual(result.circle_count, 1)
        self.assertEqual(len(ET.fromstring(svg_tonal_halftone(result, "#000")).findall(".//svg:circle", NS)), 1)
        self.assertEqual(tikz_tonal_halftone(result).count("circle [radius"), 1)

    def test_radius_cap_is_stable_at_non_round_physical_dimensions(self):
        result = tonal_halftone([[0] * 36], width_mm=138.08153439222994,
                                height_mm=423.0216227017492, dot_max_mm=4.2)
        self.assertEqual(result.circle_count, 36)
        self.assertEqual(tikz_tonal_halftone(result).count("circle [radius"), 36)

    def test_grids_reject_empty_ragged_oversized_and_invalid_samples(self):
        invalid = [[], [[]], [[0], [0, 1]], [0], "01", [[0] * 65], [[0]] * 65,
                   [[0] * 20] * 64, [[math.nan]], [[math.inf]], [[-.01]], [[1.01]], [[True]], [[".5"]]]
        for value in invalid:
            with self.subTest(value=str(value)[:60]), self.assertRaises(TonalHalftoneError):
                field(value)
        for coverage in [[[0]], [[1, 0], [0, 1]], [[-1, 1]], [[0, math.nan]]]:
            with self.subTest(coverage=coverage), self.assertRaises(TonalHalftoneError):
                field([[0, 0]], coverage=coverage)

    def test_parameters_reject_nonfinite_out_of_bounds_and_mistyped_values(self):
        invalid = [{"width_mm": 0}, {"height_mm": 501}, {"width_mm": True}, {"width_mm": 10 ** 1000},
                   {"width_mm": math.inf}, {"height_mm": "30"}, {"dot_min_mm": -.1}, {"dot_max_mm": 0},
                   {"dot_min_mm": .8, "dot_max_mm": .6}, {"dot_max_mm": 6}, {"dot_min_mm": math.nan},
                   {"gamma": 0}, {"gamma": 6}, {"gamma": math.inf}, {"gamma": True}, {"invert": 1}]
        for knobs in invalid:
            with self.subTest(knobs=knobs), self.assertRaises(TonalHalftoneError):
                tonal_halftone([[0]], **{"width_mm": 40, "height_mm": 30, **knobs})
        with self.assertRaises(TypeError):
            field([[0]], raw_svg="<image/>")

    def test_exporters_reject_injected_colors_and_malformed_pointstreams(self):
        result = field([[0]])
        for color in [None, "red", "url(https://example.test/ink)", '#123"/><image href="x"']:
            with self.subTest(color=color), self.assertRaises(TonalHalftoneError):
                svg_tonal_halftone(result, color)
        invalid = [None, dataclasses.replace(result, rows=True), dataclasses.replace(result, columns=65),
                   dataclasses.replace(result, circles=((20, 15, math.nan),)),
                   dataclasses.replace(result, circles=((0, 0, .5),)),
                   dataclasses.replace(result, circles=((20, 15, 0),)),
                   dataclasses.replace(result, circles=((20, 15, 5.1),)),
                   dataclasses.replace(result, circles=((20, 15, .5), (21, 15, .5)))]
        for value in invalid:
            for serializer in [tikz_tonal_halftone, lambda data: svg_tonal_halftone(data, "#000")]:
                with self.subTest(value=value), self.assertRaises(TonalHalftoneError):
                    serializer(value)


if __name__ == "__main__":
    unittest.main()
