"""The accent grammar stays bounded, profile-free, and equivalent across exports."""
from __future__ import annotations

import copy
import math
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sheepfling_styling.comic_accents import (  # noqa: E402
    AccentError, KINDS, svg_accent, tikz_accent, validate_accent,
)

PALETTE = {"accent": "#e94e38", "ink": "#192128", "page": "#fcfcf4", "line": "#687780"}
NS = {"svg": "http://www.w3.org/2000/svg"}


def recipe(kind="burst", width=30, height=20, **parameters):
    return {"kind": kind, "width_mm": width, "height_mm": height, "parameters": parameters}


def shape_nodes(svg):
    tree = ET.fromstring(svg)
    return list(tree.find("svg:g/svg:g", NS))


class ComicAccentTests(unittest.TestCase):
    def test_defaults_are_normalized_without_mutating_input(self):
        original = recipe("burst", rays=18)
        before = copy.deepcopy(original)
        result = validate_accent(original)
        self.assertEqual(original, before)
        self.assertEqual(result["parameters"], {"stroke_mm": 0.35, "rays": 18, "inner_ratio": 0.65, "rotation_degrees": 0.0})
        self.assertEqual(validate_accent(result), result)
        result["parameters"]["rays"] = 8
        self.assertEqual(validate_accent(original)["parameters"]["rays"], 18)

    def test_dimensions_reject_missing_non_numeric_nonfinite_and_out_of_bounds(self):
        invalid = [None, "30", True, math.nan, math.inf, -math.inf, 0, 5.9, 161, 10 ** 1000]
        for value in invalid:
            with self.subTest(value=str(value)[:30]), self.assertRaises(AccentError):
                validate_accent({"kind": "burst", "width_mm": value, "height_mm": 20})
        with self.assertRaises(AccentError):
            validate_accent(recipe(height=101))

    def test_recipe_fields_and_kind_are_closed(self):
        invalid = [[], {}, {**recipe(), "raw_tikz": "payload"}, recipe("unknown"), recipe(["burst"]),
                   {**recipe(), "parameters": []}, recipe("crosshair", rays=12)]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(AccentError):
                validate_accent(value)

    def test_parameter_bounds_and_integer_types_are_enforced(self):
        invalid = [("motion-bars", {"count": 2}), ("motion-bars", {"count": 8}), ("motion-bars", {"count": 4.0}),
                   ("motion-bars", {"count": True}), ("motion-bars", {"slant": .71}),
                   ("crosshair", {"radius_ratio": .5}), ("halftone", {"columns": 25}),
                   ("halftone", {"rows": 15}), ("halftone", {"dot_max_mm": .71}),
                   ("halftone", {"dot_min_mm": .6, "dot_max_mm": .5}), ("halftone", {"fade": "diagonal"}),
                   ("burst", {"rays": 21}), ("burst", {"inner_ratio": .9}), ("burst", {"rotation_degrees": 181}),
                   ("orbit", {"rings": 4}), ("orbit", {"tilt_degrees": 46}), ("caption-frame", {"cut_mm": .9}),
                   ("burst", {"stroke_mm": math.nan}), ("burst", {"stroke_mm": True}), ("burst", {"stroke_mm": 1.6})]
        for kind, parameters in invalid:
            with self.subTest(kind=kind, parameters=parameters), self.assertRaises(AccentError):
                validate_accent(recipe(kind, **parameters))

    def test_svg_palette_is_explicit_hex_and_cannot_inject_markup(self):
        for palette in [{}, {**PALETTE, "extra": "#000"}, {**PALETTE, "accent": 'red"/><image href="x"'},
                        {**PALETTE, "ink": "url(https://example.test/color)"}, {**PALETTE, "page": None}]:
            with self.subTest(palette=palette), self.assertRaises(AccentError):
                svg_accent(recipe(), palette)
        self.assertIn('fill="#abc"', svg_accent(recipe(), {**PALETTE, "page": "#abc"}))

    def test_all_kinds_export_deterministic_native_vectors_at_small_and_large_sizes(self):
        for kind in sorted(KINDS):
            for width, height in [(6, 6), (30, 20), (120, 70), (160, 6), (6, 100)]:
                with self.subTest(kind=kind, width=width, height=height):
                    data = recipe(kind, width, height)
                    svg, tikz = svg_accent(data, PALETTE), tikz_accent(data)
                    self.assertEqual(svg, svg_accent(data, PALETTE))
                    self.assertEqual(tikz, tikz_accent(data))
                    tree = ET.fromstring(svg)
                    self.assertEqual(tree.get("viewBox"), f"0 0 {width} {height}")
                    nodes = shape_nodes(svg)
                    self.assertGreater(len(nodes), 1)
                    self.assertLessEqual(len(nodes), 336)
                    self.assertEqual(len(nodes), tikz.count("% comic-accent primitive "))
                    self.assertNotIn("<image", svg)
                    self.assertNotIn("<text", svg)
                    self.assertNotIn("includegraphics", tikz)
                    self.assertNotIn("nan", svg.lower())
                    self.assertNotIn("inf", svg.lower())
                    self.assertIn(f"rectangle ({width},{height})", tikz)
                    for node in nodes:
                        self.assertIn(node.tag.rsplit("}", 1)[-1], {"line", "ellipse", "polygon"})

    def test_maximum_geometry_counts_are_bounded(self):
        cases = [(recipe("motion-bars", count=7), 8), (recipe("crosshair"), 4),
                 (recipe("halftone", columns=24, rows=14), 336), (recipe("burst", rays=20), 2),
                 (recipe("orbit", rings=3), 5), (recipe("caption-frame"), 3)]
        for data, expected in cases:
            with self.subTest(kind=data["kind"]):
                nodes = shape_nodes(svg_accent(data, PALETTE))
                self.assertEqual(len(nodes), expected)
                if data["kind"] == "burst":
                    self.assertEqual(len(nodes[0].get("points").split()), 40)

    def test_different_box_sizes_keep_independent_svg_clips_when_embedded(self):
        small = ET.fromstring(svg_accent(recipe(width=30, height=20), PALETTE))
        large = ET.fromstring(svg_accent(recipe(width=120, height=70), PALETTE))
        self.assertNotEqual(small.find("svg:defs/svg:clipPath", NS).get("id"),
                            large.find("svg:defs/svg:clipPath", NS).get("id"))

    def test_both_renderers_emit_identical_measured_polygon_and_ellipse_geometry(self):
        # Parsing the actual output checks coordinate parity rather than merely
        # counting calls to a shared implementation helper.
        for kind in sorted(KINDS):
            data = recipe(kind, width=77, height=38)
            svg, tikz = svg_accent(data, PALETTE), tikz_accent(data)
            tikz_records = tikz.split("% comic-accent primitive ")[1:]
            for node, record in zip(shape_nodes(svg), tikz_records, strict=True):
                tag = node.tag.rsplit("}", 1)[-1]
                self.assertTrue(record.startswith(tag))
                if tag == "polygon":
                    pairs = [tuple(map(float, point.split(","))) for point in node.get("points").split()]
                    emitted = [tuple(map(float, pair)) for pair in re.findall(r"\(([-\d.]+),([-\d.]+)\)", record)]
                    self.assertEqual(pairs, emitted)
                elif tag == "line":
                    svg_values = [float(node.get(key)) for key in ["x1", "y1", "x2", "y2"]]
                    emitted = [float(v) for pair in re.findall(r"\(([-\d.]+),([-\d.]+)\)", record) for v in pair]
                    self.assertEqual(svg_values, emitted)
                else:
                    center = re.search(r"shift=\{\(([-\d.]+),([-\d.]+)\)\}", record)
                    radii = re.search(r"x radius=([-\d.]+)mm,y radius=([-\d.]+)mm", record)
                    self.assertEqual([float(node.get("cx")), float(node.get("cy"))], list(map(float, center.groups())))
                    self.assertEqual([float(node.get("rx")), float(node.get("ry"))], list(map(float, radii.groups())))

    def test_halftone_fades_are_directional_and_cannot_overlap(self):
        for direction in ["left", "right", "up", "down"]:
            data = recipe("halftone", width=6, height=6, columns=24, rows=14, fade=direction)
            nodes = shape_nodes(svg_accent(data, PALETTE))
            radii = [float(node.get("rx")) for node in nodes]
            self.assertLessEqual(max(radii), 6 / 24 * 0.46 + 0.000001)
            start, end = (radii[0], radii[23]) if direction in {"left", "right"} else (radii[0], radii[-24])
            self.assertLess(start, end) if direction in {"right", "up"} else self.assertGreater(start, end)

    def test_geometry_contains_only_semantic_colors(self):
        for kind in sorted(KINDS):
            output = tikz_accent(recipe(kind))
            colors = set(re.findall(r"(?:fill|draw)=(\w+)", output)) - {"none"}
            self.assertTrue(colors <= {"BGAccent", "BGInk", "BGPage", "BGLine"})
            self.assertTrue(colors)


if __name__ == "__main__":
    unittest.main()
