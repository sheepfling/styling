"""Placement failures that ordinary untransformed width checks cannot catch."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
from sheepfling_styling.composition_bounds import PlacementError, guard_placement, transform_outline


class CompositionBoundsTests(unittest.TestCase):
    def test_rotation_can_cross_top_edge_despite_valid_unrotated_width(self):
        box = ((0,0),(60,0),(60,20),(0,20))
        guard_placement(transform_outline(box, origin_mm=(10,10)), region_mm=(0,0,100,60))
        with self.assertRaisesRegex(PlacementError, "exceed region"):
            guard_placement(transform_outline(box, origin_mm=(10,10), angle_degrees=12), region_mm=(0,0,100,60))

    def test_scale_is_checked_after_rotation_and_translation(self):
        box = ((0,0),(30,0),(30,10),(0,10))
        placed = transform_outline(box, origin_mm=(20,20), scale_x=1.5, scale_y=2, angle_degrees=90)
        self.assertEqual(guard_placement(placed, region_mm=(0,-30,50,60))["status"], "passed")
        with self.assertRaises(PlacementError):
            guard_placement(placed, region_mm=(0,0,50,60))

    def test_obstacle_fits_concave_notch_while_real_collision_rejects(self):
        stepped = ((0,0),(40,0),(40,10),(20,10),(20,30),(0,30))
        result = guard_placement(stepped, region_mm=(0,0,50,40), obstacles=((25,15,10,10),))
        self.assertEqual(result["checked_obstacles"], 1)
        with self.assertRaisesRegex(PlacementError, "obstacle 0"):
            guard_placement(stepped, region_mm=(0,0,50,40), obstacles=((15,15,10,10),))

    def test_region_contact_permitted_obstacle_contact_rejected(self):
        box = ((0,0),(10,0),(10,10),(0,10))
        guard_placement(box, region_mm=(0,0,10,10))
        with self.assertRaisesRegex(PlacementError, "obstacle"):
            guard_placement(box, region_mm=(0,0,20,20), obstacles=((10,10,3,3),))

    def test_clearance_rejects_near_miss(self):
        box = ((5,5),(15,5),(15,15),(5,15))
        guard_placement(box, region_mm=(0,0,30,30), obstacles=((16,5,5,10),))
        with self.assertRaises(PlacementError):
            guard_placement(box, region_mm=(0,0,30,30), clearance_mm=1, obstacles=((16,5,5,10),))

    def test_malformed_nonfinite_and_crossed_polygons_fail(self):
        good = ((0,0),(10,0),(10,10),(0,10))
        cases = [((0,0),(10,10),(0,10),(10,0)), ((0,0),(10,0),(10,0)), ((0,0),(10,0),(math.nan,10))]
        for polygon in cases:
            with self.subTest(polygon=polygon), self.assertRaises(PlacementError):
                guard_placement(polygon, region_mm=(0,0,30,30))
        for kwargs in ({"scale_x": True}, {"scale_y": 0}, {"angle_degrees": math.inf}, {"origin_mm": (0,)}):
            with self.subTest(kwargs=kwargs), self.assertRaises(PlacementError):
                transform_outline(good, **kwargs)

    def test_input_data_is_not_mutated(self):
        original = [[0,0],[10,0],[10,10],[0,10]]
        before = [list(point) for point in original]
        transform_outline(original, origin_mm=(8,9), scale_x=2, angle_degrees=6)
        self.assertEqual(original, before)


if __name__ == "__main__":
    unittest.main()
