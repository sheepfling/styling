#!/usr/bin/env python3
"""Build trusted, declarative family LaTeX compositions through shared checks.

Recipe files select local TeX sources and plain content; they never import Python
plugins. TeX remains trusted family source, even with shell execution disabled.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import unicodedata
from typing import Any
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sheepfling_styling.typography_roles import FACE_COMMANDS, tex_role_definitions, validate_role_map
from sheepfling_styling.accent_registry import (
    RECIPE_VERSIONS, accent_backend, describe_recipe_accent, svg_recipe_accent, tikz_recipe_accent,
)
from sheepfling_styling.visual_representations import validate_visual_representations
from sheepfling_styling.static_web import StaticWebError, validate_static_web
from build_family_typesetting_suite import (
    BAD_TEX, BuildError, normalize_pdf_text, pdf_page_count, run, sha256, tex,
    verify_srgb_output_intent,
)

BASELINE_PAGES = {
    "document-one-page": {1}, "document-two-page": {2}, "web-light": set(),
    "product-slick": {1, 2}, "component-proof": {6},
}
PALETTE_KEYS = {"page", "ink", "muted", "accent", "line"}
SAFE_ID = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
MACRO_ID = re.compile(r"[A-Z][A-Za-z]*\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
FONT_PATH = re.compile(r"/[A-Za-z0-9 _./()+-]+\Z")
TEX_ERRORS = re.compile(r"^!|Package\s+\S+\s+Error|LaTeX Error|Undefined control sequence|(?:[A-Z]+-)?FIT[^\n]*FAIL", re.I | re.M)


def read_object(path: Path) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise BuildError(f"Duplicate JSON key in {path}: {key}")
            result[key] = value
        return result
    try:
        if path.stat().st_size > 1_048_576:
            raise BuildError(f"Recipe input exceeds 1 MiB: {path}")
        result = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BuildError(f"Cannot read recipe input: {path}") from exc
    if not isinstance(result, dict):
        raise BuildError(f"Recipe input must be an object: {path}")
    return result


def plain(value: Any, label: str, limit: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise BuildError(f"{label} must be non-empty text of at most {limit} characters")
    if any(unicodedata.category(ch).startswith("C") for ch in value):
        raise BuildError(f"{label} contains unsupported control characters")
    return value


def number(value: Any, label: str, minimum: float, maximum: float) -> float:
    try:
        valid = type(value) in (int, float) and math.isfinite(value) and minimum <= value <= maximum
    except (OverflowError, TypeError):
        valid = False
    if not valid:
        raise BuildError(f"{label} must be a finite number from {minimum} to {maximum}")
    return float(value)


def content_value(content: dict[str, Any], dotted_path: Any) -> str:
    if not isinstance(dotted_path, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.(?:[A-Za-z_][A-Za-z0-9_]*|[0-9]+))*", dotted_path):
        raise BuildError("Content references must be dotted object keys or list indexes")
    value: Any = content
    for part in dotted_path.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isascii() and part.isdecimal() and int(part) < len(value):
            value = value[int(part)]
        else:
            raise BuildError(f"Missing content reference: {dotted_path}")
    return plain(value, f"Content reference {dotted_path}")


def relative_source(manifest_dir: Path, value: Any, label: str, suffixes: set[str]) -> Path:
    if not isinstance(value, str) or not value or "\\" in value or not re.fullmatch(r"[A-Za-z0-9_./-]+", value):
        raise BuildError(f"{label} must be a safe relative source path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {".", ".."} for part in value.split("/")) or "//" in value:
        raise BuildError(f"{label} must stay within the recipe directory")
    candidate = manifest_dir / value
    if candidate.suffix.lower() not in suffixes:
        raise BuildError(f"{label} has an unsupported source type")
    for ancestor in (candidate, *candidate.parents):
        if ancestor == manifest_dir:
            break
        if ancestor.is_symlink():
            raise BuildError(f"{label} may not use symlinks")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(manifest_dir.resolve()) or not resolved.is_file():
        raise BuildError(f"Missing or escaping {label}: {value}")
    return resolved


def pinned_source(manifest_dir: Path, record: Any, label: str, suffixes: set[str] | None = None) -> Path:
    if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
        raise BuildError(f"{label} must declare exactly path and sha256")
    path = relative_source(manifest_dir, record["path"], label, suffixes or {".tex", ".sty"})
    if not isinstance(record["sha256"], str) or not SHA.fullmatch(record["sha256"]) or sha256(path) != record["sha256"]:
        raise BuildError(f"Source hash differs from recipe: {record['path']}")
    return path


def raster_source(manifest_dir: Path, record: Any, label: str) -> dict[str, Any]:
    """Validate declared original image bytes before creating any output tree."""
    path = pinned_source(manifest_dir, record, label, {".png"})
    try:
        from PIL import Image
    except ImportError as exc:
        raise BuildError("Recipe raster assets require the optional Pillow dependency") from exc
    try:
        with Image.open(path) as image:
            if image.format != "PNG":
                raise BuildError(f"{label} must contain PNG image bytes")
            width, height = image.size
            image.verify()
        # The shared representation contract names PNG modes by their encoded
        # IHDR color type, rather than Pillow's mode (for example L or P).
        from sheepfling_styling.visual_representations import PNG_COLOR_MODES
        color_mode = PNG_COLOR_MODES.get(path.read_bytes()[25])
        if width < 1 or height < 1 or color_mode is None:
            raise BuildError(f"{label} has unsupported PNG geometry or color mode")
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
        raise BuildError(f"{label} is not a readable PNG image") from exc
    return {"path": path, "width": width, "height": height, "color_mode": color_mode}


def claim_destination(path: str, destinations: set[str], label: str) -> None:
    """Prevent sources from replacing generated files or their parent trees."""
    target = PurePosixPath(path)
    if target.parts[0] == "compiled" or any(
        target == PurePosixPath(existing) or target in PurePosixPath(existing).parents
        or PurePosixPath(existing) in target.parents for existing in destinations
    ):
        raise BuildError(f"{label} has a duplicate or reserved destination: {path}")
    destinations.add(path)


def font_source(manifest_dir: Path, face: Any, role: str) -> Path:
    if not isinstance(face, dict) or not {"path", "sha256"}.issubset(face):
        raise BuildError(f"type.{role} must declare path and sha256")
    if not isinstance(face["path"], str):
        raise BuildError(f"type.{role}.path must name a local font")
    original = Path(face["path"])
    if any(part in {".", ".."} for part in face["path"].split("/")):
        raise BuildError(f"type.{role}.path may not contain traversal")
    path = (original if original.is_absolute() else manifest_dir / original).resolve()
    if not FONT_PATH.fullmatch(str(path)) or path.suffix.lower() not in {".ttf", ".otf", ".ttc"} or not path.is_file():
        raise BuildError(f"type.{role}.path must resolve to a TeX-safe local font")
    if not isinstance(face["sha256"], str) or not SHA.fullmatch(face["sha256"]) or sha256(path) != face["sha256"]:
        raise BuildError(f"Font source hash differs from recipe: {role}")
    return path


def accent_tex(spec: Any, recipe_version: str = "0.1.0") -> str:
    if not isinstance(spec, dict) or set(spec) != {"kind", "width_mm", "height_mm", "parameters"}:
        raise BuildError("Each accent must declare kind, width_mm, height_mm, and parameters")
    number(spec["width_mm"], "accent.width_mm", 1, 300)
    number(spec["height_mm"], "accent.height_mm", 1, 300)
    if not isinstance(spec["parameters"], dict):
        raise BuildError("Accent parameters must be an object")
    try:
        return tikz_recipe_accent(spec, recipe_version)
    except (TypeError, ValueError, KeyError) as exc:
        raise BuildError(f"Invalid accent: {exc}") from exc


def duplex_metadata(output: dict[str, Any], label: str = "Output") -> dict[str, Any] | None:
    """Validate an optional logical front/back pairing, without imposing pages."""
    if "duplex" not in output:
        return None
    declaration = output["duplex"]
    fields = {"schema_version", "flip", "front_page", "back_page"}
    if not isinstance(declaration, dict) or set(declaration) != fields:
        raise BuildError(f"{label} duplex must declare exactly schema_version, flip, front_page, and back_page")
    if declaration["schema_version"] != "0.1.0":
        raise BuildError(f"{label} duplex has an unsupported schema_version")
    if not isinstance(declaration["flip"], str) or declaration["flip"] not in {"long-edge", "short-edge"}:
        raise BuildError(f"{label} duplex flip must be long-edge or short-edge")
    if type(output["page_count"]) is not int or output["page_count"] != 2:
        raise BuildError(f"{label} duplex requires page_count=2")
    if (type(declaration["front_page"]) is not int or declaration["front_page"] != 1
            or type(declaration["back_page"]) is not int or declaration["back_page"] != 2):
        raise BuildError(f"{label} duplex requires front_page=1 and back_page=2")
    return declaration | {
        "sheet_count": 1,
        "page_faces": [{"page": 1, "sheet": 1, "face": "front"},
                       {"page": 2, "sheet": 1, "face": "back"}],
        "imposition": "none", "physical_print_review": "pending",
    }


def validate_recipe(style_path: Path, content_path: Path) -> dict[str, Any]:
    style_path, content_path = style_path.resolve(), content_path.resolve()
    style, content = read_object(style_path), read_object(content_path)
    manifest_dir = style_path.parent
    required = {"recipe_version", "family_id", "display_name", "status", "type", "role_map", "palettes", "srgb_icc", "bundle_fonts", "outputs"}
    if not required.issubset(style):
        raise BuildError("Composition recipe missing: " + ", ".join(sorted(required - set(style))))
    if not isinstance(style["recipe_version"], str) or style["recipe_version"] not in RECIPE_VERSIONS:
        raise BuildError("Unsupported composition recipe version; supported: " + ", ".join(RECIPE_VERSIONS))
    if not isinstance(style["family_id"], str) or not SAFE_ID.fullmatch(style["family_id"]):
        raise BuildError("family_id must be a safe kebab-case identifier")
    plain(style["display_name"], "display_name", 100)
    plain(style["status"], "status", 100)
    if style["bundle_fonts"] is not False:
        raise BuildError("Composition recipes require bundle_fonts=false")
    if not isinstance(style["type"], dict):
        raise BuildError("Recipe type must declare physical font faces")
    try:
        validate_role_map(style["role_map"], style["type"])
    except ValueError as exc:
        raise BuildError(str(exc)) from exc
    fonts = {role: font_source(manifest_dir, face, role) for role, face in style["type"].items()}
    palettes = style["palettes"]
    if not isinstance(palettes, dict) or not palettes:
        raise BuildError("Recipe palettes must be a non-empty mapping")
    for name, palette in palettes.items():
        if not isinstance(name, str) or not SAFE_ID.fullmatch(name) or not isinstance(palette, dict) or set(palette) != PALETTE_KEYS:
            raise BuildError("Each palette needs a safe name and page, ink, muted, accent, line colors")
        if any(not isinstance(value, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", value) for value in palette.values()):
            raise BuildError("Palette colors must be six-digit RGB hex values")
    icc = relative_source(manifest_dir, style["srgb_icc"], "srgb_icc", {".icc"})
    outputs = style["outputs"]
    if not isinstance(outputs, dict) or not outputs:
        raise BuildError("Recipe outputs must be a non-empty mapping")
    raster_assets: dict[str, list[dict[str, Any]]] = {}
    for output_id, output in outputs.items():
        if not isinstance(output_id, str) or not SAFE_ID.fullmatch(output_id) or not isinstance(output, dict):
            raise BuildError("Output IDs must be safe kebab-case identifiers")
        fields = {"slot", "context", "palette", "page_count", "page", "entry", "dependencies", "bindings", "required_text", "accents"}
        if not fields.issubset(output):
            raise BuildError(f"Output {output_id} missing: {', '.join(sorted(fields - set(output)))}")
        if (output["slot"] is not None and not isinstance(output["slot"], str)) or output["slot"] not in {*BASELINE_PAGES, None} or output["slot"] == "web-light":
            raise BuildError(f"Output {output_id} has an unknown or non-PDF baseline slot")
        if not isinstance(output["context"], str) or output["context"] not in {"light", "dark", "white", "mixed"}:
            raise BuildError(f"Output {output_id} has an unsupported context")
        if not isinstance(output["palette"], str) or output["palette"] not in palettes:
            raise BuildError(f"Output {output_id} names an undeclared palette")
        if type(output["page_count"]) is not int or not 1 <= output["page_count"] <= 32:
            raise BuildError(f"Output {output_id} needs a positive page_count of at most 32")
        if output["slot"] is not None and output["page_count"] not in BASELINE_PAGES[output["slot"]]:
            raise BuildError(f"Output {output_id} page_count does not satisfy its declared baseline slot")
        duplex_metadata(output, f"Output {output_id}")
        page = output["page"]
        if not isinstance(page, dict) or set(page) != {"width_mm", "height_mm"}:
            raise BuildError(f"Output {output_id} page must declare width_mm and height_mm")
        for dimension in page:
            number(page[dimension], f"{output_id}.page.{dimension}", 50, 500)
        pinned_source(manifest_dir, output["entry"], f"{output_id}.entry")
        if Path(output["entry"]["path"]).suffix.lower() != ".tex":
            raise BuildError("Recipe entry must be a .tex document")
        deps = output["dependencies"]
        if not isinstance(deps, list):
            raise BuildError(f"Output {output_id} dependencies must be a list")
        destinations = {"generated.tex", "assets/sRGB.icc", "style.json", "content.json"}
        claim_destination(output["entry"]["path"], destinations, f"Output {output_id} entry")
        for index, dependency in enumerate(deps):
            pinned_source(manifest_dir, dependency, f"{output_id}.dependencies[{index}]")
            claim_destination(dependency["path"], destinations, f"Output {output_id} dependency")
        assets = output.get("assets", [])
        if not isinstance(assets, list):
            raise BuildError(f"Output {output_id} assets must be a list")
        raster_assets[output_id] = []
        for index, asset in enumerate(assets):
            metadata = raster_source(manifest_dir, asset, f"{output_id}.assets[{index}]")
            claim_destination(asset["path"], destinations, f"Output {output_id} asset")
            raster_assets[output_id].append(metadata)
        for key in ("bindings", "accents"):
            if not isinstance(output[key], dict):
                raise BuildError(f"Output {output_id}.{key} must be an object")
            for name in output[key]:
                if not isinstance(name, str) or not MACRO_ID.fullmatch(name):
                    raise BuildError(f"Output {output_id}.{key} names must contain PascalCase letters only")
        for reference in output["bindings"].values():
            content_value(content, reference)
        if not isinstance(output["required_text"], list) or not output["required_text"]:
            raise BuildError(f"Output {output_id} needs required_text content references")
        for reference in output["required_text"]:
            content_value(content, reference)
        for spec in output["accents"].values():
            accent_tex(spec, style["recipe_version"])
    web_plan = None
    if "web" in style:
        declaration = style["web"]
        references = declaration.get("required_text") if isinstance(declaration, dict) else None
        if not isinstance(references, list) or not references or any(not isinstance(ref, str) for ref in references):
            raise BuildError("Web required_text must be a non-empty list of content references")
        try:
            web_plan = validate_static_web(declaration, manifest_dir, palettes,
                                           {reference: content_value(content, reference) for reference in references}, style["role_map"])
        except StaticWebError as exc:
            raise BuildError(str(exc)) from exc
        # The portable recipe shares one tree with PDF sources. A web source
        # cannot replace the portable manifest, profile or any PDF source.
        for source in web_plan["sources"]:
            name = source["source_path"]
            if name in {"style.json", "content.json", style["srgb_icc"]}:
                raise BuildError(f"Web source collides with a reserved recipe source: {name}")
            for output in outputs.values():
                for record in [output["entry"], *output["dependencies"], *output.get("assets", [])]:
                    if name == record["path"] and source["sha256"] != record["sha256"]:
                        raise BuildError(f"Web and PDF source bytes conflict: {name}")
    return {"style": style, "content": content, "manifest_dir": manifest_dir, "fonts": fonts, "icc": icc,
            "raster_assets": raster_assets, "web": web_plan,
            "style_path": style_path, "content_path": content_path}


def generate_tex(style: dict[str, Any], content: dict[str, Any], output: dict[str, Any], manifest_dir: Path) -> str:
    lines = ["% Generated by the shared composition recipe runner. Edit the source manifests."]
    for role, face in style["type"].items():
        path = font_source(manifest_dir, face, role)
        lines.append("\\newfontfamily\\" + FACE_COMMANDS[role] + "{" + path.name + "}[Path={" + str(path.parent) + "/}]")
    lines.append(tex_role_definitions(style["role_map"], style["type"]))
    for name, value in style["palettes"][output["palette"]].items():
        title = name.title()
        lines.append(r"\definecolor{BG" + title + "}{HTML}{" + value[1:].upper() + "}")
        lines.append(r"\colorlet{" + title + "}{BG" + title + "}")
    for name, reference in output["bindings"].items():
        lines.append(r"\newcommand{\Field" + name + "}{" + tex(content_value(content, reference)) + "}")
    for name, spec in output["accents"].items():
        lines.append(r"\newcommand{\Accent" + name + "}{" + accent_tex(spec, style["recipe_version"]) + "}")
    lines.append(r"\newcommand{\SrgbIntent}{\special{pdf:fstream @RecipeSRGB (assets/sRGB.icc) << /N 3 >>}\special{pdf:put @catalog << /OutputIntents [ << /Type /OutputIntent /S /GTS_PDFA1 /OutputConditionIdentifier (sRGB IEC61966-2.1) /RegistryName (http://www.color.org) /Info (RGB screen layout proof) /DestOutputProfile @RecipeSRGB >> ] >>}}")
    return "\n".join(lines) + "\n"


def coverage_for_outputs(outputs: dict[str, Any], selected: tuple[str, ...] | list[str]) -> dict[str, Any]:
    coverage: dict[str, Any] = {}
    for slot in BASELINE_PAGES:
        matching = [name for name in selected if outputs[name]["slot"] == slot and outputs[name]["context"] == "light"]
        coverage[slot] = {"status": "built-awaiting-visual-review" if matching else "not-run", "outputs": matching}
    return coverage


def verify_pdf(pdf: Path, output: dict[str, Any], content: dict[str, Any], icc: Path, work: Path) -> dict[str, Any]:
    from pypdf import PdfReader
    pages = pdf_page_count(pdf, work)
    if pages != output["page_count"]:
        raise BuildError(f"{pdf.name} has {pages} pages; expected {output['page_count']}")
    reader = PdfReader(str(pdf), strict=True)
    dimensions = []
    for index, page in enumerate(reader.pages, 1):
        expected = (output["page"]["width_mm"], output["page"]["height_mm"])
        for box in (page.mediabox, page.cropbox):
            actual = (float(box.width) * 25.4 / 72, float(box.height) * 25.4 / 72)
            if any(not math.isfinite(value) or abs(value - target) > .05 for value, target in zip(actual, expected)):
                raise BuildError(f"{pdf.name} page {index} has incorrect page geometry")
        if int(page.get("/Rotate", 0)) % 360:
            raise BuildError(f"{pdf.name} page {index} has unexpected rotation")
        dimensions.append({"width_mm": round(actual[0], 4), "height_mm": round(actual[1], 4)})
    extracted = run([shutil.which("pdftotext") or "pdftotext", str(pdf), "-"], work)
    # Poppler can infer extra word spacing for rotated display type. Pypdf
    # independently reads the text objects; retain strict words in both streams.
    # Matching either preserves intentional word boundaries without deleting
    # spaces or accepting a loose sequence of individually extracted glyphs.
    pypdf_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    normalized_sources = {"poppler": normalize_pdf_text(extracted), "pypdf": normalize_pdf_text(pypdf_text)}
    text_matches = []
    for reference in output["required_text"]:
        text = content_value(content, reference)
        matches = [engine for engine, normalized in normalized_sources.items() if normalize_pdf_text(text) in normalized]
        if not matches:
            raise BuildError(f"{pdf.name} is missing required copy: {text!r}")
        text_matches.append({"reference": reference, "engines": matches})
    if any("??" in value for value in normalized_sources.values()) or "\ufffd" in extracted or "\ufffd" in pypdf_text:
        raise BuildError(f"{pdf.name} contains unresolved references or replacement glyphs")
    font_output = run([shutil.which("pdffonts") or "pdffonts", str(pdf)], work)
    rows = [line for line in font_output.splitlines()[2:] if line.strip()]
    if not rows:
        raise BuildError(f"{pdf.name} contains no embedded text fonts")
    for row in rows:
        flags = re.search(r"\s+(yes|no)\s+(yes|no)\s+(yes|no)\s+\d+\s+\d+\s*$", row)
        if not flags or flags[1] != "yes" or flags[3] != "yes":
            raise BuildError(f"{pdf.name} fonts must be embedded with Unicode maps: {row}")
    checks = {"pages": pages, "dimensions": dimensions, "embedded_fonts": True, "unicode_font_maps": True,
            "font_count": len(rows), "required_text": True,
            "text_verification": {"engines": ["poppler", "pypdf"], "matches": text_matches},
            "srgb_output_intent": verify_srgb_output_intent(pdf, icc)}
    if (duplex := duplex_metadata(output)) is not None:
        checks["duplex"] = duplex
    return checks


def build(style_path: Path, content_path: Path, output_override: Path | None = None,
          only_outputs: tuple[str, ...] | None = None, include_web: bool = False) -> dict[str, Any]:
    plan = validate_recipe(style_path, content_path)
    style, content, manifest_dir = plan["style"], plan["content"], plan["manifest_dir"]
    selected = tuple(style["outputs"]) if only_outputs is None else tuple(only_outputs)
    if not selected or len(selected) != len(set(selected)) or not set(selected).issubset(style["outputs"]):
        raise BuildError("Selected outputs must be a non-empty unique subset of the recipe outputs")
    destination = output_override if output_override is not None else style.get("output_dir")
    if destination is None:
        raise BuildError("Recipe build requires --output-dir or an output_dir in the style manifest")
    out = Path(destination).absolute()
    if out.exists() or out.is_symlink():
        raise BuildError(f"Output directory already exists; choose a new destination: {out}")
    tools = {}
    for name in ("xelatex", "pdfinfo", "pdftotext", "pdffonts", "pdftoppm"):
        executable = shutil.which(name)
        if not executable:
            raise BuildError(f"Required local tool is unavailable: {name}")
        tools[name] = {"path": executable, "version": run([executable, "--version" if name == "xelatex" else "-v"], manifest_dir).splitlines()[0]}
    try:
        import pypdf  # noqa: F401
    except ImportError as exc:
        raise BuildError("Recipe PDF verification requires pypdf") from exc
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    compiled_roots = {out / "editable-source" / output_id / "compiled" for output_id in selected}

    def packet_file(path: Path) -> bool:
        # A declared source may legitimately contain a nested `compiled`
        # segment. Exclude only this runner's actual build directories.
        return path.is_file() and not any(path.is_relative_to(directory) for directory in compiled_roots)

    report: dict[str, Any] = {
        "schema_version": 1, "recipe_version": style["recipe_version"], "family_id": style["family_id"],
        "display_name": style["display_name"], "status": "building", "source_status": style["status"],
        "created_at": datetime.now(timezone.utc).isoformat(), "screen_proof_only": True,
        "production_ready": False, "visual_review": "pending", "selected_outputs": list(selected),
        "font_files_copied": False, "font_dependencies": [
            {"role": role, "path": str(path), "sha256": sha256(path), "included_in_package": False}
            for role, path in plan["fonts"].items()],
        "type_role_map": style["role_map"], "tools": tools,
        "runner_sha256": sha256(Path(__file__)),
        "shared_renderer_sha256": sha256(ROOT / "scripts/build_family_typesetting_suite.py"),
        "shared_dependencies": {
            path.relative_to(ROOT).as_posix(): sha256(path) for path in (
                ROOT / "src/sheepfling_styling/typography_roles.py",
                ROOT / "src/sheepfling_styling/accent_registry.py",
                ROOT / "src/sheepfling_styling/comic_accents.py",
                ROOT / "src/sheepfling_styling/visual_representations.py",
                ROOT / "contracts/composition-recipe.json",
                ROOT / "contracts/typography-deliverable-suite.json",
            )
        },
        "inputs": {"style": {"path": str(plan["style_path"]), "sha256": sha256(plan["style_path"])},
                   "content": {"path": str(plan["content_path"]), "sha256": sha256(plan["content_path"])}},
        "coverage": {slot: {"status": "not-run", "outputs": []} for slot in BASELINE_PAGES},
        "web": {"status": "not-run", "requested": include_web, "reason": f"Composition recipe {style['recipe_version']} builds PDF proofs only"},
        "pdfs": {}, "previews": {}, "accents": {}, "assets": {},
        "limits": ["Trusted family TeX source; shell execution is disabled, not a TeX sandbox.",
                   "System font files are required and omitted from the editable package.",
                   "RGB screen proof; browser and physical print verification remain separate."],
    }
    if plan["web"] is not None:
        report["shared_dependencies"]["src/sheepfling_styling/static_web.py"] = sha256(ROOT / "src/sheepfling_styling/static_web.py")
        report["web"]["reason"] = "Static web proof requested" if include_web else "Omitted for a bounded PDF review (--no-web)"
    for output_id in selected:
        for spec in style["outputs"][output_id]["accents"].values():
            dependency = accent_backend(spec["kind"], style["recipe_version"])["source_path"]
            report["shared_dependencies"][dependency] = sha256(ROOT / dependency)
    def write_report() -> None:
        (out / "build-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report()
    try:
        # A bounded, manifest-relative rebuild packet complements each staged
        # compile source. System fonts remain explicit external dependencies.
        rebuild = out / "recipe-input"
        rebuild.mkdir()
        portable_style = json.loads(json.dumps(style))
        portable_style["outputs"] = {name: portable_style["outputs"][name] for name in selected}
        portable_style["output_dir"] = "rebuilt"
        if not include_web:
            portable_style.pop("web", None)
        for role, path in plan["fonts"].items():
            portable_style["type"][role]["path"] = str(path)
        for output_id in selected:
            for record in [style["outputs"][output_id]["entry"], *style["outputs"][output_id]["dependencies"],
                           *style["outputs"][output_id].get("assets", [])]:
                target = rebuild / record["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(manifest_dir / record["path"], target)
        target_icc = rebuild / style["srgb_icc"]
        target_icc.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(plan["icc"], target_icc)
        if include_web and plan["web"] is not None:
            for source in plan["web"]["sources"]:
                target = rebuild / source["source_path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(plan["web"]["files"][source["path"]])
        (rebuild / "style.json").write_text(json.dumps(portable_style, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        shutil.copyfile(plan["content_path"], rebuild / "content.json")
        report["rebuild_recipe"] = {"style": "recipe-input/style.json", "content": "recipe-input/content.json",
            "selected_outputs": list(selected), "font_dependencies_included": False}
        duplex_outputs = {name: pairing for name in selected
                          if (pairing := duplex_metadata(style["outputs"][name])) is not None}
        if duplex_outputs:
            report["rebuild_recipe"]["duplex"] = duplex_outputs
        if include_web and plan["web"] is not None:
            web_plan = plan["web"]
            sources = []
            for source in web_plan["sources"]:
                target = out / "web" / source["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(web_plan["files"][source["path"]])
                sources.append(source | {"path": target.relative_to(out).as_posix(),
                                          "source_origin": str(manifest_dir / source["source_path"])})
            web_metadata = {"interface_id": "family-static-web-source", "interface_version": "0.1.0",
                            "schema_version": 1, "sources": sources,
                            "rendering": "Family-owned native HTML/CSS with declared local assets; no browser rendering performed"}
            web_metadata_path = out / "web-representations.json"
            web_metadata_path.write_text(json.dumps(web_metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            report["web"] = {"id": style["web"]["id"], "status": "static-checks-passed-awaiting-browser-review",
                             "requested": True, "context": style["web"]["context"], "palette": style["web"]["palette"],
                             "entry": "web/" + web_plan["entry"], "sources": sources, "checks": web_plan["checks"],
                             "representation_metadata": {"path": "web-representations.json", "sha256": sha256(web_metadata_path)},
                             "font_files_copied": False, "browser_review": "pending"}
            report["rebuild_recipe"]["web_included"] = True
        pdf_dir = out / "pdf"
        pdf_dir.mkdir()
        representations = []
        for output_id in selected:
            output = style["outputs"][output_id]
            work = out / "editable-source" / output_id
            work.mkdir(parents=True)
            records = [output["entry"], *output["dependencies"], *output.get("assets", [])]
            if output["accents"]:
                accent_dir = out / "accents" / output_id
                accent_dir.mkdir(parents=True)
                palette = style["palettes"][output["palette"]]
                report["accents"][output_id] = {}
                for name, accent in output["accents"].items():
                    vector = accent_dir / (name + ".svg")
                    vector.write_text(svg_recipe_accent(accent, {key: palette[key] for key in ("accent", "ink", "page", "line")}, style["recipe_version"]), encoding="utf-8")
                    implementation = describe_recipe_accent(accent, style["recipe_version"])
                    report["accents"][output_id][name] = {"path": vector.relative_to(out).as_posix(),
                        "sha256": sha256(vector), "recipe": accent, "palette": palette,
                        "implementation": implementation,
                        "generation": "Generated editable SVG geometry; the PDF uses the same recipe through native TikZ."}
                    representations.append({"id": output_id + "-" + name, "representation": "vector-master",
                        "path": vector.relative_to(out).as_posix(), "sha256": sha256(vector),
                        "linked_raster_sources": [], "editable": True,
                        "generated_from": {"style_sha256": sha256(plan["style_path"]), "output_id": output_id, "accent": name,
                            "recipe_version": style["recipe_version"], "kind": accent["kind"]},
                        "generator": implementation["svg_generator"]})
            for record in records:
                source = pinned_source(manifest_dir, record, f"{output_id} source", {".tex", ".sty", ".png"})
                target = work / record["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            report["assets"][output_id] = []
            for index, (record, metadata) in enumerate(zip(output.get("assets", []), plan["raster_assets"][output_id]), 1):
                asset_path = (work / record["path"]).relative_to(out).as_posix()
                representation = {"id": f"raster-source:{output_id}:{index}", "representation": "raster-source",
                    "path": asset_path, "sha256": record["sha256"], "width": metadata["width"],
                    "height": metadata["height"], "color_mode": metadata["color_mode"],
                    "master_status": "no-vector-master"}
                representations.append(representation)
                report["assets"][output_id].append(representation | {"source_path": str(metadata["path"])})
            (work / "assets").mkdir(exist_ok=True)
            shutil.copyfile(plan["icc"], work / "assets/sRGB.icc")
            shutil.copyfile(plan["style_path"], work / "style.json")
            shutil.copyfile(plan["content_path"], work / "content.json")
            (work / "generated.tex").write_text(generate_tex(style, content, output, manifest_dir), encoding="utf-8")
            staged_files = [path for path in sorted(work.rglob("*")) if path.is_file()]
            source_paths = [path.relative_to(out).as_posix() for path in staged_files]
            source_hashes = {path.relative_to(out).as_posix(): sha256(path) for path in staged_files}
            compiled = work / "compiled"
            compiled.mkdir()
            command = [tools["xelatex"]["path"], "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error",
                       "-file-line-error", f"-jobname={output_id}", f"-output-directory={compiled}", output["entry"]["path"]]
            log_output = "FIRST PASS\n" + run(command, work) + "\nSECOND PASS\n" + run(command, work)
            (work / "xelatex-output.txt").write_text(log_output, encoding="utf-8")
            log = (compiled / (output_id + ".log")).read_text(encoding="utf-8", errors="replace")
            errors = BAD_TEX.findall(log) + TEX_ERRORS.findall(log)
            if errors:
                raise BuildError(f"{output_id} contains TeX/font layout errors: {' | '.join(errors[:10])}")
            source_pdf = compiled / (output_id + ".pdf")
            if not source_pdf.is_file():
                raise BuildError(f"XeLaTeX did not create {output_id}.pdf")
            checks = verify_pdf(source_pdf, output, content, work / "assets/sRGB.icc", work)
            pdf = pdf_dir / (output_id + ".pdf")
            shutil.copyfile(source_pdf, pdf)
            preview_dir = out / "previews" / output_id
            preview_dir.mkdir(parents=True)
            run([tools["pdftoppm"]["path"], "-png", "-r", "120", str(pdf), str(preview_dir / "page")], work)
            previews = sorted(preview_dir.glob("page-*.png"))
            if len(previews) != output["page_count"]:
                raise BuildError(f"{output_id} preview count differs from page_count")
            report["pdfs"][output_id] = {"path": pdf.relative_to(out).as_posix(), "sha256": sha256(pdf),
                "bytes": pdf.stat().st_size, "slot": output["slot"], "context": output["context"], "palette": output["palette"],
                "page": output["page"], "palette_colors": style["palettes"][output["palette"]],
                "checks": checks | {"tex_layout_errors": 0}, "source_hashes": source_hashes,
                "source_origins": [{"path": str(manifest_dir / record["path"]), "sha256": record["sha256"], "staged_path": (work / record["path"]).relative_to(out).as_posix()} for record in records],
                "fit_diagnostics": [line.strip() for line in log.splitlines() if "FIT" in line],
                "visual_review": "pending", "accent_system": output["accents"]}
            if (duplex := duplex_metadata(output)) is not None:
                report["pdfs"][output_id]["duplex"] = duplex
            report["previews"][output_id] = [{"path": path.relative_to(out).as_posix(), "sha256": sha256(path)} for path in previews]
            representations.append({"id": output_id, "representation": "derived-export", "path": pdf.relative_to(out).as_posix(),
                "sha256": sha256(pdf), "source_paths": source_paths, "generator": "scripts/build_recipe_suite.py + XeLaTeX",
                "rendering": "Native LaTeX text and family-owned TikZ vector composition"
                    + (" with declared raster illustrations" if output.get("assets") else "")
                    + "; RGB screen proof", "format": "PDF",
                "page_count": output["page_count"], "page_map": [{"page": index, "source_paths": source_paths} for index in range(1, output["page_count"] + 1)]})
            write_report()
        metadata = {"interface_id": "visual-asset-representations", "interface_version": "0.1.0", "schema_version": 1,
                    "representations": representations}
        raw = (json.dumps(metadata, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        (out / "representations.json").write_bytes(raw)
        files = {path.relative_to(out).as_posix(): path.read_bytes() for path in out.rglob("*") if packet_file(path)}
        report["representation_checks"] = validate_visual_representations(raw, files)
        report["coverage"] = coverage_for_outputs(style["outputs"], selected)
        if include_web and plan["web"] is not None and style["web"]["context"] == "light":
            report["coverage"]["web-light"] = {"status": "static-checks-passed-awaiting-browser-review",
                                               "outputs": [style["web"]["id"]]}
        report["status"] = "checks-passed-awaiting-visual-review"
        write_report()
        (out / "README.md").write_text(
            f"# {style['display_name']} composition proofs\n\n"
            "Trusted editable LaTeX sources, generated content, RGB profile, PDFs, previews, and exact-byte evidence are included. "
            "Font binaries are omitted; the declared local fonts are required to compile the staged source. "
            "Run XeLaTeX twice from an output's editable-source directory using its declared entry. "
            "Regenerate from edited JSON with this repository's build_family_typesetting_suite.py "
            "--style recipe-input/style.json --content recipe-input/content.json --output-dir rebuilt"
            + (". Native static web sources are included under web/; browser verification requires separate exact-byte evidence. "
               if include_web and plan["web"] is not None else " --no-web. ") +
            "The package is a local screen proof awaiting visual review; it does not establish browser or press readiness.\n", encoding="utf-8")
        archive_version = "_".join(style["recipe_version"].split(".")[:2])
        archive_path = out / (style["family_id"] + "_Composition_Proofs_" + archive_version + ".zip")
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(out.rglob("*")):
                if packet_file(path) and path != archive_path and path.suffix.lower() not in {".ttf", ".otf", ".ttc"}:
                    archive.write(path, path.relative_to(out))
        return report | {"output_dir": str(out), "editable_source_zip": str(archive_path), "zip_bytes": archive_path.stat().st_size, "zip_sha256": sha256(archive_path)}
    except Exception as exc:
        report.update({"status": "rejected", "error": str(exc)})
        write_report()
        raise
