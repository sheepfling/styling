"""Measured stepped silhouettes preserve indents and share safe render geometry."""
from __future__ import annotations

import copy
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sheepfling_styling.lockup_geometry import (  # noqa: E402
    LockupGeometryError, measure_lockup, polygon_tikz,
)


def row(width=40, height=10, x=0, y=0):
    return {"width_mm": width, "height_mm": height, "x_mm": x, "y_mm": y}


class LockupGeometryTests(unittest.TestCase):
    def test_indented_rows_have_a_measured_stepped_outline(self):
        result = measure_lockup([row(30, x=10), row(50, y=10), row(42, x=5, y=20)],
                                angle_degrees=0, padding_mm=0)
        self.assertEqual(result["outline"], ((10.0, 0.0), (40.0, 0.0), (40.0, 10.0),
                                           (50.0, 10.0), (50.0, 20.0), (47.0, 20.0),
                                           (47.0, 30.0), (5.0, 30.0), (5.0, 20.0),
                                           (0.0, 20.0), (0.0, 10.0), (10.0, 10.0)))
        self.assertEqual(result["bounds_mm"], (0.0, 0.0, 50.0, 30.0))
        self.assertEqual((result["width_mm"], result["height_mm"]), (50.0, 30.0))
        self.assertIsNone(result["shadow_outline"])
        self.assertIsNone(result["transformed_shadow_outline"])

    def test_overlapping_rows_and_padding_preserve_only_exterior_steps(self):
        result = measure_lockup([row(20), row(30, x=-5, y=9)], angle_degrees=0, padding_mm=1)
        self.assertEqual(result["outline"], ((-1.0, -1.0), (21.0, -1.0), (21.0, 8.0),
                                           (26.0, 8.0), (26.0, 20.0), (-6.0, 20.0),
                                           (-6.0, 8.0), (-1.0, 8.0)))

    def test_one_row_is_a_rectangle_and_fully_contained_rows_add_no_steps(self):
        one = measure_lockup([row(30, 20)], angle_degrees=0, padding_mm=0)
        contained = measure_lockup([row(30, 20), row(10, 5, x=10, y=5)],
                                  angle_degrees=0, padding_mm=0)
        self.assertEqual(one, contained)
        self.assertEqual(one["outline"], ((0.0, 0.0), (30.0, 0.0), (30.0, 20.0), (0.0, 20.0)))

    def test_all_rotated_padded_corners_and_shadow_fit_bounds(self):
        lines = [row(31, 11, x=-4, y=-5), row(59, 10, x=-13, y=6), row(46, 9, x=-2, y=16)]
        for angle in (-20, -4, 0, 4, 20):
            with self.subTest(angle=angle):
                result = measure_lockup(lines, angle_degrees=angle, padding_mm=1.5, extrusion_mm=3)
                xmin, ymin, xmax, ymax = result["bounds_mm"]
                radians = math.radians(angle)
                for line in lines:
                    for x in (line["x_mm"] - 1.5, line["x_mm"] + line["width_mm"] + 1.5):
                        for y in (line["y_mm"] - 1.5, line["y_mm"] + line["height_mm"] + 1.5):
                            for offset in (0, 3):
                                tx = math.cos(radians) * (x + offset) + math.sin(radians) * (y + offset)
                                ty = -math.sin(radians) * (x + offset) + math.cos(radians) * (y + offset)
                                self.assertGreaterEqual(tx + 1e-12, xmin)
                                self.assertLessEqual(tx - 1e-12, xmax)
                                self.assertGreaterEqual(ty + 1e-12, ymin)
                                self.assertLessEqual(ty - 1e-12, ymax)
                self.assertEqual(result["width_mm"], xmax - xmin)
                self.assertEqual(result["height_mm"], ymax - ymin)

    def test_positive_angle_rises_to_right_and_extrusion_offsets_locally(self):
        result = measure_lockup([row()], angle_degrees=4, padding_mm=0, extrusion_mm=2)
        left, right = result["transformed_outline"][:2]
        self.assertLess(right[1], left[1])
        self.assertEqual(result["shadow_outline"], tuple((x + 2, y + 2) for x, y in result["outline"]))

    def test_measurement_is_deterministic_and_does_not_mutate_input(self):
        lines = [row(), row(50, y=10)]
        original = copy.deepcopy(lines)
        first = measure_lockup(lines, extrusion_mm=1)
        self.assertEqual(first, measure_lockup(lines, extrusion_mm=1))
        self.assertEqual(lines, original)
        self.assertNotIn("text", first)

    def test_gap_disconnected_and_unsorted_rows_are_rejected(self):
        cases = [[row(), row(y=15)], [row(), row(x=40, y=10)],
                 [row(), row(x=45, y=9)], [row(y=10), row(y=0)]]
        for lines in cases:
            with self.subTest(lines=lines), self.assertRaises(LockupGeometryError):
                measure_lockup(lines, padding_mm=0)
        # Measured whitespace may be covered by the explicit padding budget.
        self.assertTrue(measure_lockup([row(), row(y=12)], padding_mm=1)["outline"])

    def test_inputs_are_bounded_finite_numeric_and_closed(self):
        for lines in (None, "rows", [], [row()] * 9, [{}], [{**row(), "text": "a"}],
                      [{key: value for key, value in row().items() if key != "x_mm"}]):
            with self.subTest(lines=lines), self.assertRaises(LockupGeometryError):
                measure_lockup(lines)
        for key in row():
            for invalid in (None, True, "10", math.nan, math.inf, -math.inf, 10 ** 1000):
                with self.subTest(key=key, invalid=str(invalid)[:20]), self.assertRaises(LockupGeometryError):
                    measure_lockup([{**row(), key: invalid}])
        for key in ("width_mm", "height_mm"):
            for invalid in (0, -1, 300.01):
                with self.subTest(key=key, invalid=invalid), self.assertRaises(LockupGeometryError):
                    measure_lockup([{**row(), key: invalid}])
        for key in ("x_mm", "y_mm"):
            for invalid in (-300.01, 300.01):
                with self.subTest(key=key, invalid=invalid), self.assertRaises(LockupGeometryError):
                    measure_lockup([{**row(), key: invalid}])
        for kwargs in ({"angle_degrees": 20.01}, {"angle_degrees": -20.01},
                       {"padding_mm": -0.1}, {"padding_mm": 6.01},
                       {"extrusion_mm": -0.1}, {"extrusion_mm": 6.01},
                       {"angle_degrees": math.nan}, {"padding_mm": True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(LockupGeometryError):
                measure_lockup([row()], **kwargs)

    def test_tikz_path_has_only_bounded_numeric_geometry(self):
        self.assertEqual(polygon_tikz([(0, -0.0), (10.5, 0), (0, 8.125)]),
                         "(0mm,0mm) -- (10.5mm,0mm) -- (0mm,8.125mm) -- cycle")
        points = measure_lockup([row(), row(50, y=10)])["transformed_outline"]
        self.assertEqual(polygon_tikz(points), polygon_tikz(points))
        for invalid in ([], [(0, 0)] * 129, [(0, 0), (1, 0), (0, math.nan)],
                        [(0, 0), (1, 0), (0, "\\input{payload}")],
                        [(0, 0), (1, 0), (0, 1000.01)], [(0, 0), (1, 0), (1, 2, 3)]):
            with self.subTest(points=invalid), self.assertRaises(LockupGeometryError):
                polygon_tikz(invalid)


if __name__ == "__main__":
    unittest.main()
