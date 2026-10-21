"""Version boundaries, exact legacy output, and native CLI integration."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from sheepfling_styling.accent_registry import (
    ACCENT_KINDS_BY_VERSION, RECIPE_VERSIONS, accent_backend, describe_recipe_accent,
    svg_recipe_accent, tikz_recipe_accent, validate_recipe_accent,
)
from sheepfling_styling.comic_accents import KINDS, svg_accent, tikz_accent, validate_accent
from sheepfling_styling.narrative_marks import narrative_mark, svg_narrative_mark, tikz_narrative_mark
from sheepfling_styling.typography_roles import SHARED_TYPE_ROLES
import build_recipe_suite as BUILDER

PALETTE = {"ink": "#18283C", "page": "#F7F3EB", "accent": "#C93463", "line": "#667B91"}
NEW_KINDS = ("trajectory-fan", "registration-tab", "scratch-slashes", "cut-keyline")


def recipe(kind, width=60, height=36, **parameters):
    return {"kind": kind, "width_mm": width, "height_mm": height, "parameters": parameters}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def real_font():
    for path in (Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
                 Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")):
        if path.is_file():
            return path
    return None


def write_cli_fixture(directory: Path, actual_font: Path | None = None):
    """A neutral, fully pinned 0.2 specimen exercising all four added kinds."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "compositions").mkdir()
    (directory / "assets").mkdir()
    entry = directory / "compositions/main.tex"
    entry.write_text(r"""\documentclass{article}
\usepackage[paperwidth=210mm,paperheight=148mm,margin=0mm]{geometry}
\usepackage{fontspec,xcolor,tikz}
\input{generated.tex}
\input{compositions/components.tex}
\pagestyle{empty}
\begin{document}\SrgbIntent\pagecolor{BGPage}\color{BGInk}\null
\begin{tikzpicture}[remember picture,overlay]
\node[anchor=north west,inner sep=0pt] at([xshift=14mm,yshift=-12mm]current page.north west){\TypeDocumentTitle\fontsize{20}{22}\selectfont\FieldTitle};
\node[anchor=north west,inner sep=0pt] at([xshift=14mm,yshift=-28mm]current page.north west){\TypeLabel\fontsize{9}{10}\selectfont TRAJECTORY FAN};
\node[anchor=north west,inner sep=0pt] at([xshift=112mm,yshift=-28mm]current page.north west){\TypeLabel\fontsize{9}{10}\selectfont REGISTRATION TAB};
\node[anchor=north west,inner sep=0pt] at([xshift=14mm,yshift=-35mm]current page.north west){\AccentFan};
\node[anchor=north west,inner sep=0pt] at([xshift=112mm,yshift=-35mm]current page.north west){\AccentTab};
\node[anchor=north west,inner sep=0pt] at([xshift=14mm,yshift=-80mm]current page.north west){\TypeLabel\fontsize{9}{10}\selectfont SCRATCH SLASHES};
\node[anchor=north west,inner sep=0pt] at([xshift=112mm,yshift=-80mm]current page.north west){\TypeLabel\fontsize{9}{10}\selectfont CUT KEYLINE};
\node[anchor=north west,inner sep=0pt] at([xshift=14mm,yshift=-87mm]current page.north west){\AccentScratch};
\node[anchor=north west,inner sep=0pt] at([xshift=112mm,yshift=-87mm]current page.north west){\AccentKeyline};
\node[anchor=north west,inner sep=0pt] at([xshift=14mm,yshift=-133mm]current page.north west){\TypeBody\fontsize{9}{11}\selectfont\FieldStatus\quad\FixtureDependency};
\end{tikzpicture}
\end{document}
""", encoding="utf-8")
    dependency = directory / "compositions/components.tex"
    dependency.write_text(r"\newcommand{\FixtureDependency}{PINNED SOURCE}", encoding="utf-8")
    if actual_font:
        from PIL import ImageCms
        (directory / "assets/sRGB.icc").write_bytes(ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())
        face = {"path": str(actual_font), "sha256": digest(actual_font)}
    else:
        font = directory / "synthetic.ttf"
        font.write_bytes(b"synthetic file used for input validation only")
        face = {"path": "synthetic.ttf", "sha256": digest(font)}
        (directory / "assets/sRGB.icc").write_bytes(b"synthetic ICC used for input validation only")
    style = {
        "recipe_version": "0.2.0", "family_id": "synthetic-accent-study", "display_name": "Synthetic accent study",
        "status": "synthetic-native-integration-proof", "type": {key: deepcopy(face) for key in ("body", "display", "strong")},
        "role_map": {key: "body" for key in SHARED_TYPE_ROLES},
        "palettes": {"paper": PALETTE | {"muted": "#526174"}}, "srgb_icc": "assets/sRGB.icc", "bundle_fonts": False,
        "outputs": {"mark-study": {"slot": None, "context": "light", "palette": "paper", "page_count": 1,
            "page": {"width_mm": 210, "height_mm": 148},
            "entry": {"path": "compositions/main.tex", "sha256": digest(entry)},
            "dependencies": [{"path": "compositions/components.tex", "sha256": digest(dependency)}],
            "bindings": {"Title": "title", "Status": "status"}, "required_text": ["title", "status"],
            "accents": {"Fan": recipe("trajectory-fan"), "Tab": recipe("registration-tab", 60, 24),
                        "Scratch": recipe("scratch-slashes", 50, 18, cut_style="straight"), "Keyline": recipe("cut-keyline")}}},
    }
    style_path, content_path = directory / "style.json", directory / "content.json"
    style_path.write_text(json.dumps(style, indent=2) + "\n", encoding="utf-8")
    content_path.write_text(json.dumps({"title": "One grammar, four native accents", "status": "SYNTHETIC LOCAL PROOF"}), encoding="utf-8")
    return style_path, content_path, style


class AccentRegistryTests(unittest.TestCase):
    def test_contract_matches_closed_version_kind_sets(self):
        contract = json.loads((ROOT / "contracts/composition-recipe.json").read_text())
        self.assertEqual(tuple(contract["supported_recipe_versions"]), RECIPE_VERSIONS)
        for version in RECIPE_VERSIONS:
            self.assertEqual(set(contract["accent_grammars"][version]["kinds"]), ACCENT_KINDS_BY_VERSION[version])
        self.assertEqual(ACCENT_KINDS_BY_VERSION["0.1.0"], KINDS)
        self.assertEqual(ACCENT_KINDS_BY_VERSION["0.2.0"] - KINDS, set(NEW_KINDS))

    def test_legacy_native_bytes_are_identical_through_both_versions(self):
        for kind in KINDS:
            spec = recipe(kind)
            for version in RECIPE_VERSIONS:
                with self.subTest(kind=kind, version=version):
                    self.assertEqual(validate_recipe_accent(spec, version), validate_accent(spec))
                    self.assertEqual(tikz_recipe_accent(spec, version), tikz_accent(spec))
                    self.assertEqual(svg_recipe_accent(spec, PALETTE, version), svg_accent(spec, PALETTE))

    def test_new_kinds_require_explicit_new_version(self):
        for kind in NEW_KINDS:
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "not supported by recipe 0.1.0"):
                tikz_recipe_accent(recipe(kind), "0.1.0")
        for version in (None, [], "0.4.0"):
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, "Unsupported composition recipe"):
                accent_backend("crosshair", version)

    def test_technical_kinds_require_03_and_prior_02_bytes_are_preserved(self):
        from sheepfling_styling.technical_marks import svg_technical_mark,tikz_technical_mark
        for spec in (recipe("concentric-rings",24,24),recipe("signal-rule",60,18)):
            for version in ("0.1.0","0.2.0"):
                with self.assertRaisesRegex(ValueError,"not supported by recipe"):
                    validate_recipe_accent(spec,version)
            self.assertEqual(tikz_recipe_accent(spec,"0.3.0"),tikz_technical_mark(spec))
            self.assertEqual(svg_recipe_accent(spec,PALETTE,"0.3.0"),svg_technical_mark(spec,PALETTE))
            self.assertTrue(describe_recipe_accent(spec,"0.3.0")["source_path"].endswith("technical_marks.py"))
        for kind in NEW_KINDS:
            spec=recipe(kind)
            self.assertEqual(tikz_recipe_accent(spec,"0.2.0"),tikz_recipe_accent(spec,"0.3.0"))
            self.assertEqual(svg_recipe_accent(spec,PALETTE,"0.2.0"),svg_recipe_accent(spec,PALETTE,"0.3.0"))

    @unittest.skipUnless(all(shutil.which(tool) for tool in ("xelatex","pdfinfo","pdftotext","pdffonts","pdftoppm")) and real_font(),"native tools unavailable")
    def test_actual_03_cli_records_new_backend_geometry_and_version_boundary(self):
        if not importlib.util.find_spec("PIL") or not importlib.util.find_spec("pypdf"):
            self.skipTest("optional native verification dependencies unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);style_path,content_path,style=write_cli_fixture(root/"input",real_font())
            accents=style["outputs"]["mark-study"]["accents"]
            accents["Fan"]=recipe("concentric-rings",36,36,rings=6)
            accents["Tab"]=recipe("signal-rule",60,24)
            # A new kind under the old grammar must fail before output creation.
            style_path.write_text(json.dumps(style))
            with self.assertRaisesRegex(BUILDER.BuildError,"not supported by recipe 0.2.0"):
                BUILDER.build(style_path,content_path,root/"rejected")
            self.assertFalse((root/"rejected").exists())
            style["recipe_version"]="0.3.0";style_path.write_text(json.dumps(style))
            out=root/"proof"
            completed=subprocess.run([sys.executable,str(ROOT/"scripts/build_family_typesetting_suite.py"),"--style",str(style_path),
                            "--content",str(content_path),"--output-dir",str(out),"--no-web"],cwd=ROOT,check=True,capture_output=True,text=True)
            report=json.loads((out/"build-report.json").read_text())
            backend="src/sheepfling_styling/technical_marks.py"
            self.assertEqual(report["shared_dependencies"][backend],digest(ROOT/backend))
            self.assertEqual(report["pdfs"]["mark-study"]["checks"]["pages"],1)
            for name in ("Fan","Tab"):
                item=report["accents"]["mark-study"][name]
                self.assertEqual(item["implementation"]["normalized_recipe"]["kind"],accents[name]["kind"])
                self.assertEqual((out/item["path"]).read_text(),svg_recipe_accent(accents[name],PALETTE,"0.3.0"))
            with zipfile.ZipFile(json.loads(completed.stdout)["editable_source_zip"]) as packet:
                self.assertFalse(any(Path(n).suffix in {".ttf",".otf",".ttc",".woff",".woff2"} for n in packet.namelist()))

    def test_narrative_exports_use_the_same_geometry_and_anchor_metadata(self):
        for kind in NEW_KINDS[:2]:
            spec = recipe(kind)
            mark = narrative_mark(spec)
            self.assertEqual(tikz_recipe_accent(spec, "0.2.0"), tikz_narrative_mark(mark))
            self.assertEqual(svg_recipe_accent(spec, PALETTE, "0.2.0"), svg_narrative_mark(mark, PALETTE))
            description = describe_recipe_accent(spec, "0.2.0")
            self.assertEqual(len(description["label_anchors"]), len(mark.label_anchors))
            self.assertTrue(description["source_path"].endswith("narrative_marks.py"))
            self.assertNotIn("<text", svg_recipe_accent(spec, PALETTE, "0.2.0"))

    def test_finish_exports_are_direct_native_helpers_with_explicit_palette(self):
        from sheepfling_styling.comic_finishes import svg_finish, tikz_finish
        for kind in NEW_KINDS[2:]:
            spec = recipe(kind)
            self.assertEqual(tikz_recipe_accent(spec, "0.2.0"), tikz_finish(spec))
            self.assertEqual(svg_recipe_accent(spec, PALETTE, "0.2.0"), svg_finish(spec, PALETTE))
            with self.assertRaises(ValueError):
                svg_recipe_accent(spec, {"ink": "#000000"}, "0.2.0")

    def test_kind_specific_bounds_and_unknown_code_fields_reject(self):
        invalid = [recipe("trajectory-fan", arms=True), recipe("registration-tab", rail_width_mm=100),
                   recipe("scratch-slashes", strength=float("nan")), recipe("cut-keyline", echo="true"),
                   recipe("scratch-slashes", module="os"), recipe("__import__('os')"), recipe(["crosshair"])]
        for spec in invalid:
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                validate_recipe_accent(spec, "0.2.0")
        with self.assertRaises(ValueError):
            describe_recipe_accent([], "0.2.0")

    def test_runner_uses_explicit_version_before_creating_output(self):
        with tempfile.TemporaryDirectory() as directory:
            style_path, content_path, style = write_cli_fixture(Path(directory))
            BUILDER.validate_recipe(style_path, content_path)
            style["recipe_version"] = "0.1.0"
            style_path.write_text(json.dumps(style))
            with self.assertRaisesRegex(BUILDER.BuildError, "not supported by recipe 0.1.0"):
                BUILDER.build(style_path, content_path, Path(directory) / "must-not-exist")
            self.assertFalse((Path(directory) / "must-not-exist").exists())

    @unittest.skipUnless(all(shutil.which(tool) for tool in ("xelatex", "pdfinfo", "pdftotext", "pdffonts", "pdftoppm")) and real_font(), "native XeLaTeX/Poppler/font integration tools unavailable")
    def test_actual_shared_cli_builds_four_added_kinds_with_hashes_and_no_font_zip(self):
        if not importlib.util.find_spec("PIL") or not importlib.util.find_spec("pypdf"):
            self.skipTest("optional native verification dependencies unavailable")
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            style_path, content_path, style = write_cli_fixture(base / "input", real_font())
            out = base / "proof"
            command = [sys.executable, str(ROOT / "scripts/build_family_typesetting_suite.py"),
                       "--style", str(style_path), "--content", str(content_path), "--output-dir", str(out), "--only", "mark-study", "--no-web"]
            completed = subprocess.run(command, cwd=ROOT, check=True, text=True, capture_output=True)
            returned = json.loads(completed.stdout)
            report = json.loads((out / "build-report.json").read_text())
            self.assertEqual(report["recipe_version"], "0.2.0")
            self.assertEqual(report["pdfs"]["mark-study"]["checks"]["pages"], 1)
            self.assertEqual(report["representation_checks"]["vector_master_count"], 4)
            self.assertEqual(report["representation_checks"]["derived_export_count"], 1)
            self.assertTrue(all(item["status"] == "not-run" for item in report["coverage"].values()))
            for source in ("accent_registry.py", "narrative_marks.py", "comic_finishes.py"):
                path = "src/sheepfling_styling/" + source
                self.assertEqual(report["shared_dependencies"][path], digest(ROOT / path))
            vectors = report["accents"]["mark-study"]
            for name, spec in style["outputs"]["mark-study"]["accents"].items():
                self.assertEqual((out / vectors[name]["path"]).read_text(), svg_recipe_accent(spec, PALETTE, "0.2.0"))
                self.assertEqual(vectors[name]["implementation"]["recipe_version"], "0.2.0")
                self.assertEqual(vectors[name]["sha256"], digest(out / vectors[name]["path"]))
            self.assertEqual(report["font_dependencies"][0]["sha256"], digest(real_font()))
            with zipfile.ZipFile(returned["editable_source_zip"]) as archive:
                self.assertFalse(any(Path(name).suffix.lower() in {".ttf", ".otf", ".ttc", ".woff", ".woff2"} for name in archive.namelist()))
                self.assertEqual(hashlib.sha256(archive.read("pdf/mark-study.pdf")).hexdigest(), report["pdfs"]["mark-study"]["sha256"])
                self.assertEqual(hashlib.sha256(archive.read("recipe-input/compositions/components.tex")).hexdigest(), style["outputs"]["mark-study"]["dependencies"][0]["sha256"])
            (style_path.parent / "compositions/components.tex").write_text("changed source")
            rejected = subprocess.run(command[:command.index("--output-dir")+1] + [str(base / "rejected"), "--no-web"], cwd=ROOT, text=True, capture_output=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("Source hash differs", rejected.stderr)
            self.assertFalse((base / "rejected").exists())


if __name__ == "__main__":
    unittest.main()
