"""Neutral recipe validation and composition-boundary regression checks."""
from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from contextlib import redirect_stderr
from io import StringIO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("composition_recipe_builder", ROOT / "scripts/build_recipe_suite.py")
BUILDER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(BUILDER)

# A complete, one-pixel grayscale PNG keeps validation fixtures independent of
# image generation libraries while exercising real raster bytes and metadata.
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGP4/x8AAwAB//wl3FEAAAAASUVORK5CYII=")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class CompositionRecipeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        (self.root / "compositions").mkdir()
        (self.root / "assets").mkdir()
        (self.root / "compositions/main.tex").write_text("% trusted synthetic composition\n", encoding="utf-8")
        (self.root / "compositions/components.sty").write_text("% synthetic component\n", encoding="utf-8")
        (self.root / "assets/sRGB.icc").write_bytes(b"synthetic ICC; only validation uses this fixture")
        font = self.root / "synthetic.ttf"
        font.write_bytes(b"synthetic font; only validation uses this fixture")
        face = {"path": "synthetic.ttf", "sha256": digest(font.read_bytes())}
        self.style = {
            "recipe_version": "0.1.0", "family_id": "synthetic-family", "display_name": "Synthetic family",
            "status": "local-prototype", "type": {name: deepcopy(face) for name in ("body", "display", "strong", "mono")},
            "role_map": {},
            "palettes": {"light": {"page": "#FFFFFF", "ink": "#111111", "muted": "#555555", "accent": "#66FF00", "line": "#888888"}},
            "srgb_icc": "assets/sRGB.icc", "bundle_fonts": False,
            "outputs": {"one-page": {"slot": "document-one-page", "context": "light", "palette": "light", "page_count": 1,
                "page": {"width_mm": 210, "height_mm": 148},
                "entry": {"path": "compositions/main.tex", "sha256": digest((self.root / "compositions/main.tex").read_bytes())},
                "dependencies": [{"path": "compositions/components.sty", "sha256": digest((self.root / "compositions/components.sty").read_bytes())}],
                "bindings": {"Title": "editorial.lines.0", "Body": "editorial.body"},
                "required_text": ["editorial.lines.0"], "accents": {
                    "Motion": {"kind": "motion-bars", "width_mm": 24, "height_mm": 8, "parameters": {"count": 3}}}}},
        }
        from sheepfling_styling.typography_roles import SHARED_TYPE_ROLES
        self.style["role_map"] = {role: "body" for role in SHARED_TYPE_ROLES}
        self.style["role_map"]["annotation"] = "mono"
        self.content = {"editorial": {"lines": ["A clear premise"], "body": "Literal & 50% #1_ remains plain copy."}}
        self.style_path, self.content_path = self.root / "style.json", self.root / "content.json"
        self.write()

    def tearDown(self):
        self.directory.cleanup()

    def write(self):
        self.style_path.write_text(json.dumps(self.style), encoding="utf-8")
        self.content_path.write_text(json.dumps(self.content), encoding="utf-8")

    def validate(self):
        self.write()
        return BUILDER.validate_recipe(self.style_path, self.content_path)

    def declare_asset(self, path="assets/illustration.png"):
        asset = self.root / path
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_bytes(PNG)
        self.style["outputs"]["one-page"]["assets"] = [{"path": path, "sha256": digest(PNG)}]
        return asset

    def build_fixture(self, out, include_web=False, only_outputs=None):
        """Exercise real staging/provenance/ZIP checks with synthetic TeX output."""
        def fake_run(command, work):
            if "-no-shell-escape" in command:
                compiled = Path(next(arg.split("=", 1)[1] for arg in command if arg.startswith("-output-directory=")))
                job = next(arg.split("=", 1)[1] for arg in command if arg.startswith("-jobname="))
                (compiled / (job + ".log")).write_text("clean fixture log", encoding="utf-8")
                (compiled / (job + ".pdf")).write_bytes(b"%PDF-1.7\nsynthetic compiled proof\n")
            elif "-png" in command:
                output_id = Path(command[-2]).stem
                for page in range(1, self.style["outputs"][output_id]["page_count"] + 1):
                    Path(command[-1] + f"-{page}.png").write_bytes(PNG)
            return "synthetic tool 1.0\n"

        with patch.object(BUILDER.shutil, "which", side_effect=lambda name: "/tools/" + name), \
             patch.object(BUILDER, "run", side_effect=fake_run), \
             patch.object(BUILDER, "verify_pdf", side_effect=lambda pdf, output, *_: {"pages": output["page_count"]}):
            return BUILDER.build(self.style_path, self.content_path, out, include_web=include_web,
                                 only_outputs=only_outputs)

    def declare_web(self):
        from test_static_web import fixture_sources
        self.style["web"] = fixture_sources(self.root)
        self.style["web"]["palette"] = "light"
        from sheepfling_styling.typography_roles import css_role_definitions
        css = self.root / "web/styles.css"
        css.write_text(css.read_text() + '\n:root {--face-mono: "Sample Mono", monospace;}\n'
                       + css_role_definitions(self.style["role_map"], self.style["type"]), encoding="utf-8")
        self.style["web"]["dependencies"][0]["sha256"] = digest(css.read_bytes())
        self.write()

    def test_declared_native_web_is_staged_and_packaged_with_separate_evidence(self):
        self.declare_web()
        out = self.root / "web-output"
        report = self.build_fixture(out, include_web=True)
        self.assertEqual(report["web"]["entry"], "web/index.html")
        self.assertEqual(report["web"]["checks"]["shared_type_role_selectors"], 17)
        self.assertEqual(report["coverage"]["web-light"], {
            "status": "static-checks-passed-awaiting-browser-review", "outputs": ["web-light"]})
        self.assertEqual(report["web"]["browser_review"], "pending")
        self.assertEqual((out / "web/index.html").read_bytes(), (self.root / "web/index.html").read_bytes())
        representations = json.loads((out / "representations.json").read_text())["representations"]
        self.assertTrue(all(not entry["path"].startswith("web/") for entry in representations))
        web_metadata = json.loads((out / "web-representations.json").read_text())
        self.assertEqual(web_metadata["interface_id"], "family-static-web-source")
        self.assertTrue(any(source["representation"] == "linked-pdf-document" for source in web_metadata["sources"]))
        self.assertIn("src/sheepfling_styling/static_web.py", report["shared_dependencies"])
        with zipfile.ZipFile(report["editable_source_zip"]) as archive:
            self.assertEqual(archive.read("web/styles.css"), (self.root / "web/styles.css").read_bytes())
            self.assertEqual(archive.read("recipe-input/web/assets/brief.pdf"), (self.root / "web/assets/brief.pdf").read_bytes())
            self.assertFalse(any(name.endswith((".ttf", ".otf", ".ttc", ".woff", ".woff2")) for name in archive.namelist()))
            unpacked = self.root / "unpacked-web"
            archive.extractall(unpacked)
        plan = BUILDER.validate_recipe(unpacked / "recipe-input/style.json", unpacked / "recipe-input/content.json")
        self.assertEqual(plan["web"]["files"]["styles.css"], (self.root / "web/styles.css").read_bytes())

    def test_no_web_omits_declared_web_and_retains_a_valid_bounded_rebuild(self):
        self.declare_web()
        out = self.root / "pdf-only-output"
        report = self.build_fixture(out)
        self.assertFalse((out / "web").exists())
        self.assertFalse((out / "web-representations.json").exists())
        self.assertEqual(report["coverage"]["web-light"]["status"], "not-run")
        self.assertIn("--no-web", report["web"]["reason"])
        portable = json.loads((out / "recipe-input/style.json").read_text())
        self.assertNotIn("web", portable)
        self.assertIsNone(BUILDER.validate_recipe(out / "recipe-input/style.json", out / "recipe-input/content.json")["web"])
        with zipfile.ZipFile(report["editable_source_zip"]) as archive:
            self.assertFalse(any(name.startswith(("web/", "recipe-input/web/")) for name in archive.namelist()))

    def test_bad_declared_web_rejects_before_creating_any_output(self):
        self.declare_web()
        self.style["web"]["entry"]["sha256"] = "0" * 64
        self.write()
        out = self.root / "rejected-web-output"
        with self.assertRaisesRegex(BUILDER.BuildError, "Web source hash differs"):
            self.build_fixture(out, include_web=True)
        self.assertFalse(out.exists())

    def test_absent_or_dark_web_cannot_receive_light_web_coverage(self):
        out = self.root / "absent-web-output"
        report = self.build_fixture(out, include_web=True)
        self.assertEqual(report["web"]["status"], "not-run")
        self.assertEqual(report["coverage"]["web-light"]["status"], "not-run")
        self.declare_web()
        self.style["web"]["context"] = "dark"
        self.write()
        report = self.build_fixture(self.root / "dark-web-output", include_web=True)
        self.assertEqual(report["web"]["status"], "static-checks-passed-awaiting-browser-review")
        self.assertEqual(report["coverage"]["web-light"]["status"], "not-run")

    def test_neutral_recipe_accepts_manifest_relative_fonts_and_sources(self):
        plan = self.validate()
        self.assertEqual(plan["fonts"]["body"], (self.root / "synthetic.ttf").resolve())
        self.assertEqual(plan["icc"], (self.root / "assets/sRGB.icc").resolve())
        self.assertEqual(plan["raster_assets"], {"one-page": []})

    def test_optional_assets_accept_real_png_and_capture_encoded_metadata(self):
        asset = self.declare_asset("art/engravings/planet.png")
        plan = self.validate()
        self.assertEqual(plan["raster_assets"]["one-page"], [{
            "path": asset.resolve(), "width": 1, "height": 1, "color_mode": "Grayscale with alpha"}])

    def test_asset_hash_and_missing_files_reject_before_output_creation(self):
        asset = self.declare_asset()
        output = self.style["outputs"]["one-page"]
        for issue in ("hash", "missing"):
            with self.subTest(issue=issue):
                if issue == "hash":
                    output["assets"][0]["sha256"] = "0" * 64
                else:
                    output["assets"][0]["sha256"] = digest(PNG)
                    asset.unlink()
                self.write()
                out = self.root / "unused-output"
                with self.assertRaises(BUILDER.BuildError):
                    BUILDER.build(self.style_path, self.content_path, out)
                self.assertFalse(out.exists())

    def test_asset_paths_types_symlinks_and_non_png_bytes_reject(self):
        asset = self.declare_asset()
        output = self.style["outputs"]["one-page"]
        record = output["assets"][0]
        for bad in ("../outside.png", "/absolute.png", "assets\\bad.png", "assets/./illustration.png", "assets//illustration.png",
                    "assets/illustration.jpg", "assets/illustration.jpeg", "assets/illustration.svg", "assets/illustration.tex"):
            with self.subTest(path=bad):
                record["path"] = bad
                with self.assertRaises(BUILDER.BuildError):
                    self.validate()
        record["path"] = "assets/illustration.png"
        (self.root / "linked-art").symlink_to(self.root / "assets", target_is_directory=True)
        record["path"] = "linked-art/illustration.png"
        with self.assertRaisesRegex(BUILDER.BuildError, "symlink"):
            self.validate()
        record["path"] = "assets/illustration.png"
        asset.write_bytes(b"not a PNG")
        record["sha256"] = digest(asset.read_bytes())
        with self.assertRaisesRegex(BUILDER.BuildError, "readable PNG"):
            self.validate()

    def test_asset_records_must_be_exact_and_asset_list_must_be_a_list(self):
        self.declare_asset()
        output = self.style["outputs"]["one-page"]
        output["assets"][0]["extra"] = True
        with self.assertRaisesRegex(BUILDER.BuildError, "exactly path and sha256"):
            self.validate()
        output["assets"] = {}
        with self.assertRaisesRegex(BUILDER.BuildError, "assets must be a list"):
            self.validate()

    def test_asset_destinations_cannot_duplicate_or_enter_reserved_trees(self):
        self.declare_asset()
        output = self.style["outputs"]["one-page"]
        output["assets"].append(deepcopy(output["assets"][0]))
        with self.assertRaisesRegex(BUILDER.BuildError, "duplicate or reserved"):
            self.validate()
        for bad in ("compiled/illustration.png", "generated.tex/illustration.png"):
            with self.subTest(path=bad):
                self.declare_asset(bad)
                with self.assertRaisesRegex(BUILDER.BuildError, "duplicate or reserved"):
                    self.validate()
        # Collision checks also cover parent destinations and ICC/template paths,
        # even when their normal extension checks would reject the same input.
        for bad in ("assets/sRGB.icc", "compositions/main.tex", "assets", "content.json/illustration.png"):
            with self.subTest(path=bad), self.assertRaisesRegex(BUILDER.BuildError, "duplicate or reserved"):
                BUILDER.claim_destination(bad, {"assets/sRGB.icc", "compositions/main.tex", "content.json"}, "asset")

    def test_declared_unused_rasters_stage_package_and_link_to_pdf_provenance(self):
        self.declare_asset("art/engravings/planet.png")
        outputs = self.style["outputs"]
        outputs["other-page"] = deepcopy(outputs["one-page"])
        self.write()
        out = self.root / "asset-output"
        report = self.build_fixture(out)
        self.assertFalse(report["font_files_copied"])
        self.assertEqual(report["representation_checks"]["raster_source_count"], 2)
        self.assertEqual((out / "recipe-input/art/engravings/planet.png").read_bytes(), PNG)
        for output_id in outputs:
            staged = f"editable-source/{output_id}/art/engravings/planet.png"
            self.assertEqual((out / staged).read_bytes(), PNG)
            self.assertEqual(report["pdfs"][output_id]["source_hashes"][staged], digest(PNG))
            self.assertIn(staged, [entry["staged_path"] for entry in report["pdfs"][output_id]["source_origins"]])
        representations = json.loads((out / "representations.json").read_text())["representations"]
        self.assertEqual(len({entry["id"] for entry in representations}), len(representations))
        for entry in representations:
            if entry["representation"] == "derived-export":
                self.assertTrue(any(path.endswith("planet.png") for path in entry["source_paths"]))
        with zipfile.ZipFile(report["editable_source_zip"]) as archive:
            self.assertEqual(archive.read("recipe-input/art/engravings/planet.png"), PNG)
            self.assertFalse(any(name.endswith(".ttf") for name in archive.namelist()))
        portable = json.loads((out / "recipe-input/style.json").read_text())
        self.assertEqual(portable["outputs"]["one-page"]["assets"], outputs["one-page"]["assets"])

    def test_nested_compiled_sources_survive_representation_checks_and_rebuild_zip(self):
        self.declare_asset("art/compiled/planet.png")
        self.style["outputs"]["compiled"] = self.style["outputs"].pop("one-page")
        icc = self.root / "profiles/compiled/sRGB.icc"
        icc.parent.mkdir(parents=True)
        icc.write_bytes((self.root / "assets/sRGB.icc").read_bytes())
        self.style["srgb_icc"] = "profiles/compiled/sRGB.icc"
        self.write()
        out = self.root / "nested-compiled-output"
        report = self.build_fixture(out)
        self.assertEqual(report["representation_checks"]["status"], "passed")
        staged = "editable-source/compiled/art/compiled/planet.png"
        self.assertEqual(report["pdfs"]["compiled"]["source_hashes"][staged], digest(PNG))
        with zipfile.ZipFile(report["editable_source_zip"]) as archive:
            self.assertEqual(archive.read(staged), PNG)
            self.assertEqual(archive.read("recipe-input/profiles/compiled/sRGB.icc"), icc.read_bytes())
            self.assertFalse(any(name.startswith("editable-source/compiled/compiled/") for name in archive.namelist()))
            unpacked = self.root / "unpacked"
            archive.extractall(unpacked)
        # Revalidating the actual extracted rebuild recipe catches omitted ICC
        # and image dependencies, rather than just checking the ZIP filenames.
        plan = BUILDER.validate_recipe(unpacked / "recipe-input/style.json", unpacked / "recipe-input/content.json")
        self.assertEqual(plan["raster_assets"]["compiled"][0]["path"].read_bytes(), PNG)
        self.assertEqual(plan["icc"].read_bytes(), icc.read_bytes())

    def test_shared_cli_preserves_an_occupied_dangling_symlink_destination(self):
        import build_family_typesetting_suite as entrypoint
        occupied = self.root / "occupied-output"
        target = self.root / "missing-target"
        occupied.symlink_to(target, target_is_directory=True)
        arguments = ["build", "--style", str(self.style_path), "--content", str(self.content_path),
                     "--output-dir", str(occupied), "--no-web"]
        error = StringIO()
        with patch.object(sys, "argv", arguments), redirect_stderr(error):
            result = entrypoint.main()
        self.assertEqual(result, 2)
        self.assertIn("already exists", error.getvalue())
        self.assertTrue(occupied.is_symlink())
        self.assertFalse(target.exists())

    def test_generated_tex_escapes_copy_and_uses_declared_semantic_faces(self):
        self.validate()
        source = BUILDER.generate_tex(self.style, self.content, self.style["outputs"]["one-page"], self.root)
        self.assertIn(r"\newcommand{\FieldTitle}{A clear premise}", source)
        self.assertIn(r"Literal \& 50\% \#1\_", source)
        self.assertIn(r"\newcommand{\TypeAnnotation}{\MonoFace}", source)
        self.assertIn(r"\newcommand{\AccentMotion}{\begin{tikzpicture}", source)
        self.assertIn(r"\definecolor{BGPage}{HTML}{FFFFFF}", source)
        self.assertIn(r"\newcommand{\SrgbIntent}", source)

    def test_sources_reject_path_traversal_absolute_and_backslash_paths(self):
        for bad in ("../escape.tex", "/absolute.tex", "compositions\\escape.tex", "compositions/./main.tex", "compositions//main.tex"):
            with self.subTest(bad=bad):
                entry = self.style["outputs"]["one-page"]["entry"]
                previous = entry["path"]
                entry["path"] = bad
                with self.assertRaises(BUILDER.BuildError):
                    self.validate()
                entry["path"] = previous

    def test_source_hash_mismatch_rejects_before_output_creation(self):
        self.style["outputs"]["one-page"]["dependencies"][0]["sha256"] = "0" * 64
        self.write()
        out = self.root / "unused-output"
        with self.assertRaisesRegex(BUILDER.BuildError, "Source hash differs"):
            BUILDER.build(self.style_path, self.content_path, out)
        self.assertFalse(out.exists())

    def test_symlink_source_and_symlink_parent_reject(self):
        original = self.style["outputs"]["one-page"]["entry"]
        (self.root / "linked").symlink_to(self.root / "compositions", target_is_directory=True)
        self.style["outputs"]["one-page"]["entry"] = {"path": "linked/main.tex", "sha256": original["sha256"]}
        with self.assertRaisesRegex(BUILDER.BuildError, "symlink"):
            self.validate()

    def test_duplicate_and_reserved_dependency_destinations_reject(self):
        output = self.style["outputs"]["one-page"]
        output["dependencies"].append(deepcopy(output["dependencies"][0]))
        with self.assertRaisesRegex(BUILDER.BuildError, "duplicate or reserved"):
            self.validate()
        output["dependencies"] = [deepcopy(output["entry"])]
        with self.assertRaisesRegex(BUILDER.BuildError, "duplicate or reserved"):
            self.validate()

    def test_font_hash_bundling_and_role_map_are_explicit(self):
        self.style["type"]["body"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(BUILDER.BuildError, "Font source hash"):
            self.validate()
        self.style["type"]["body"]["sha256"] = self.style["type"]["display"]["sha256"]
        self.style["bundle_fonts"] = True
        with self.assertRaisesRegex(BUILDER.BuildError, "bundle_fonts=false"):
            self.validate()
        self.style["bundle_fonts"] = False
        self.style["role_map"].pop("annotation")
        with self.assertRaisesRegex(BUILDER.BuildError, "every shared semantic"):
            self.validate()

    def test_coverage_only_credits_selected_light_context(self):
        outputs = self.style["outputs"]
        outputs["dark-proof"] = deepcopy(outputs["one-page"])
        outputs["dark-proof"]["context"] = "dark"
        outputs["marks"] = deepcopy(outputs["one-page"])
        outputs["marks"]["slot"] = None
        coverage = BUILDER.coverage_for_outputs(outputs, ("dark-proof", "marks"))
        self.assertTrue(all(row["status"] == "not-run" for row in coverage.values()))
        coverage = BUILDER.coverage_for_outputs(outputs, ("one-page", "marks"))
        self.assertEqual(coverage["document-one-page"]["outputs"], ["one-page"])
        self.assertEqual(coverage["web-light"]["status"], "not-run")

    def test_duplex_accepts_explicit_front_back_pairing_independently_of_accent_version_and_slot(self):
        output = self.style["outputs"]["one-page"]
        output["page_count"] = 2
        for version in ("0.1.0", "0.2.0", "0.3.0"):
            self.style["recipe_version"] = version
            for slot in (None, "product-slick", "document-two-page"):
                output["slot"] = slot
                for flip in ("long-edge", "short-edge"):
                    output["duplex"] = {"schema_version": "0.1.0", "flip": flip, "front_page": 1, "back_page": 2}
                    with self.subTest(version=version, slot=slot, flip=flip):
                        self.assertEqual(self.validate()["style"]["outputs"]["one-page"]["duplex"], output["duplex"])

    def test_duplex_rejects_unknown_fields_wrong_types_versions_faces_and_page_counts(self):
        output = self.style["outputs"]["one-page"]
        output["slot"], output["page_count"] = None, 2
        valid = {"schema_version": "0.1.0", "flip": "long-edge", "front_page": 1, "back_page": 2}
        declarations = [None, False, [], {}, {key: value for key, value in valid.items() if key != "flip"},
                        valid | {"imposed": True}]
        declarations.extend(valid | {key: value} for key, values in {
            "schema_version": ["0.2.0", 1, None], "flip": ["both", None, []],
            "front_page": [True, 0, 2, 1.0, "1"], "back_page": [True, 1, 3, 2.0, "2"],
        }.items() for value in values)
        for declaration in declarations:
            output["duplex"] = declaration
            with self.subTest(declaration=declaration), self.assertRaisesRegex(BUILDER.BuildError, "duplex"):
                self.validate()
        output["duplex"] = valid
        for count in (1, 3, True):
            output["page_count"] = count
            with self.subTest(page_count=count), self.assertRaisesRegex(BUILDER.BuildError, "page_count"):
                self.validate()
        output["page_count"], output["duplex"] = 2, valid | {"front_page": 2, "back_page": 1}
        self.write()
        out = self.root / "rejected-duplex"
        with self.assertRaisesRegex(BUILDER.BuildError, "front_page=1 and back_page=2"):
            self.build_fixture(out)
        self.assertFalse(out.exists())

    def test_duplex_report_and_extracted_rebuild_preserve_pairing_without_changing_other_outputs(self):
        output = deepcopy(self.style["outputs"]["one-page"])
        declaration = {"schema_version": "0.1.0", "flip": "long-edge", "front_page": 1, "back_page": 2}
        output.update(slot="product-slick", page_count=2, duplex=declaration)
        self.style["outputs"]["front-back"] = output
        self.write()
        report = self.build_fixture(self.root / "duplex-output")
        expected = declaration | {"sheet_count": 1,
            "page_faces": [{"page": 1, "sheet": 1, "face": "front"}, {"page": 2, "sheet": 1, "face": "back"}],
            "imposition": "none", "physical_print_review": "pending"}
        self.assertEqual(report["pdfs"]["front-back"]["duplex"], expected)
        self.assertEqual(report["rebuild_recipe"]["duplex"], {"front-back": expected})
        self.assertNotIn("duplex", report["pdfs"]["one-page"])
        with zipfile.ZipFile(report["editable_source_zip"]) as archive:
            unpacked = self.root / "unpacked-duplex"
            archive.extractall(unpacked)
            archived_report = json.loads(archive.read("build-report.json"))
        self.assertEqual(archived_report["pdfs"]["front-back"]["duplex"], expected)
        portable = BUILDER.validate_recipe(unpacked / "recipe-input/style.json", unpacked / "recipe-input/content.json")
        self.assertEqual(portable["style"]["outputs"]["front-back"]["duplex"], declaration)
        self.assertNotIn("duplex", portable["style"]["outputs"]["one-page"])
        bounded = self.build_fixture(self.root / "nonduplex-output", only_outputs=("one-page",))
        self.assertNotIn("duplex", bounded["rebuild_recipe"])
        self.assertEqual(set(bounded["pdfs"]), {"one-page"})

    def test_duplex_verifier_records_pairing_only_after_both_native_page_geometries_pass(self):
        from pypdf import PdfWriter
        output = self.style["outputs"]["one-page"]
        output.update(slot="product-slick", page_count=2,
                      duplex={"schema_version": "0.1.0", "flip": "short-edge", "front_page": 1, "back_page": 2})
        pdf = self.root / "front-back.pdf"
        fonts = "name type encoding emb sub uni object ID\n--- --- --- --- --- --- --- ---\nTest TrueType Custom yes yes yes 1 0\n"
        for back_width, back_rotation, expected_error in (
            (210, 0, None), (200, 0, "page 2 has incorrect page geometry"),
            (210, 180, "page 2 has unexpected rotation"),
        ):
            writer = PdfWriter()
            writer.add_blank_page(width=210 * 72 / 25.4, height=148 * 72 / 25.4)
            back = writer.add_blank_page(width=back_width * 72 / 25.4, height=148 * 72 / 25.4)
            if back_rotation:
                back.rotate(back_rotation)
            with pdf.open("wb") as stream:
                writer.write(stream)
            with patch.object(BUILDER, "pdf_page_count", return_value=2), \
                 patch.object(BUILDER, "run", side_effect=["A clear premise", fonts]), \
                 patch.object(BUILDER, "verify_srgb_output_intent", return_value={"status": "passed"}):
                if expected_error:
                    with self.assertRaisesRegex(BUILDER.BuildError, expected_error):
                        BUILDER.verify_pdf(pdf, output, self.content, self.root / "assets/sRGB.icc", self.root)
                else:
                    checks = BUILDER.verify_pdf(pdf, output, self.content, self.root / "assets/sRGB.icc", self.root)
                    self.assertEqual(checks["duplex"]["page_faces"], [
                        {"page": 1, "sheet": 1, "face": "front"}, {"page": 2, "sheet": 1, "face": "back"}])
                    self.assertEqual(checks["duplex"]["flip"], "short-edge")
                    self.assertEqual(checks["duplex"]["physical_print_review"], "pending")
                    self.assertEqual(len(checks["dimensions"]), 2)

    def test_unknown_slots_wrong_counts_and_nonfinite_geometry_reject(self):
        output = self.style["outputs"]["one-page"]
        output["slot"] = "invented"
        with self.assertRaisesRegex(BUILDER.BuildError, "slot"):
            self.validate()
        output["slot"] = "component-proof"
        with self.assertRaisesRegex(BUILDER.BuildError, "page_count"):
            self.validate()
        output["slot"] = "document-one-page"
        for bad in (float("nan"), float("inf"), True, 0, 501):
            output["page"]["width_mm"] = bad
            with self.subTest(bad=bad), self.assertRaisesRegex(BUILDER.BuildError, "finite number"):
                self.validate()

    def test_missing_content_nonstring_leaves_and_invalid_macro_names_reject(self):
        output = self.style["outputs"]["one-page"]
        output["bindings"]["Title"] = "editorial.missing"
        with self.assertRaisesRegex(BUILDER.BuildError, "Missing content"):
            self.validate()
        output["bindings"]["Title"] = "editorial.lines"
        with self.assertRaisesRegex(BUILDER.BuildError, "non-empty text"):
            self.validate()
        output["bindings"] = {"Title2": "editorial.lines.0"}
        with self.assertRaisesRegex(BUILDER.BuildError, "PascalCase"):
            self.validate()

    def test_invalid_accent_parameters_reject(self):
        self.style["outputs"]["one-page"]["accents"]["Motion"]["parameters"]["count"] = True
        with self.assertRaisesRegex(BUILDER.BuildError, "Invalid accent"):
            self.validate()

    def test_duplicate_json_keys_and_unsupported_recipe_version_reject(self):
        self.style_path.write_text('{"recipe_version":"0.1.0","recipe_version":"0.2.0"}', encoding="utf-8")
        with self.assertRaisesRegex(BUILDER.BuildError, "Duplicate JSON"):
            BUILDER.validate_recipe(self.style_path, self.content_path)
        self.style["recipe_version"] = "9.0.0"
        with self.assertRaisesRegex(BUILDER.BuildError, "Unsupported composition"):
            self.validate()

    def test_broken_symlink_output_is_occupied(self):
        self.write()
        out = self.root / "occupied-output"
        out.symlink_to(self.root / "nonexistent")
        with self.assertRaisesRegex(BUILDER.BuildError, "already exists"):
            BUILDER.build(self.style_path, self.content_path, out)

    def test_unknown_selected_output_rejects_before_output_creation(self):
        self.write()
        out = self.root / "unused-output"
        with self.assertRaisesRegex(BUILDER.BuildError, "Selected outputs"):
            BUILDER.build(self.style_path, self.content_path, out, only_outputs=("missing",))
        self.assertFalse(out.exists())

    def test_geometry_verifier_rejects_actual_wrong_page_size(self):
        from pypdf import PdfWriter
        pdf = self.root / "wrong.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        with pdf.open("wb") as stream:
            writer.write(stream)
        with patch.object(BUILDER, "pdf_page_count", return_value=1):
            with self.assertRaisesRegex(BUILDER.BuildError, "page geometry"):
                BUILDER.verify_pdf(pdf, self.style["outputs"]["one-page"], self.content, self.root / "assets/sRGB.icc", self.root)

    def test_rotated_text_can_match_independent_pypdf_stream_without_removing_spaces(self):
        from pypdf import PdfWriter
        pdf = self.root / "rotated.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=210 * 72 / 25.4, height=148 * 72 / 25.4)
        with pdf.open("wb") as stream:
            writer.write(stream)
        self.content["editorial"]["lines"][0] = "COMPLEX IDEAS"
        fonts = "name type encoding emb sub uni object ID\n--- --- --- --- --- --- --- ---\nTest TrueType Custom yes yes yes 1 0\n"
        with patch.object(BUILDER, "pdf_page_count", return_value=1), \
             patch.object(BUILDER, "run", side_effect=["COMP L E X I DE A S", fonts]), \
             patch.object(BUILDER, "verify_srgb_output_intent", return_value={"status": "passed"}), \
             patch("pypdf._page.PageObject.extract_text", return_value="COMPLEX IDEAS"):
            checks = BUILDER.verify_pdf(pdf, self.style["outputs"]["one-page"], self.content, self.root / "assets/sRGB.icc", self.root)
        self.assertEqual(checks["text_verification"]["matches"][0]["engines"], ["pypdf"])
        # Neither extractor may turn arbitrary internally-spaced glyphs into a
        # matching word by deleting spaces; the second independent stream must
        # actually contain the intended phrase.
        with patch.object(BUILDER, "pdf_page_count", return_value=1), \
             patch.object(BUILDER, "run", return_value="COMP L E X I DE A S"), \
             patch("pypdf._page.PageObject.extract_text", return_value="COMP L E X I DE A S"):
            with self.assertRaisesRegex(BUILDER.BuildError, "missing required copy"):
                BUILDER.verify_pdf(pdf, self.style["outputs"]["one-page"], self.content, self.root / "assets/sRGB.icc", self.root)

    def test_contract_declares_version_and_does_not_replace_legacy_contract(self):
        contract = json.loads((ROOT / "contracts/composition-recipe.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["recipe_version"], "0.3.0")
        self.assertEqual(contract["supported_recipe_versions"], ["0.1.0", "0.2.0", "0.3.0"])
        self.assertFalse(contract["fonts"]["bundle_fonts"])
        self.assertIn("mono", contract["fonts"]["optional_physical_faces"])
        self.assertEqual(contract["outputs"]["baseline_pdf_slots"]["component-proof"], [6])
        self.assertIn("duplex", contract["outputs"]["optional_fields"])
        self.assertEqual(contract["outputs"]["duplex"]["required_page_count"], 2)
        self.assertFalse(contract["outputs"]["duplex"]["additional_fields"])


if __name__ == "__main__":
    unittest.main()
