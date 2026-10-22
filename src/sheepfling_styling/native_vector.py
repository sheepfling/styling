"""Build exact, family-owned SVG compositions without replacing their layout."""
from __future__ import annotations

import hashlib
import base64
import json
import posixpath
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from typing import Any

from .pdf_output_intent import add_srgb_output_intent
from .family_coverage import coverage_from_outputs
from .visual_representations import PNG_COLOR_MODES, PNG_SIGNATURE, validate_visual_representations

HASH = re.compile(r"[0-9a-f]{64}\Z")
ID = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
LENGTH = re.compile(r"(\d+(?:\.\d+)?)pt\Z")
SVG_TAG = "{http://www.w3.org/2000/svg}svg"
BASELINE = {"document-one-page", "product-slick"}


class NativeVectorError(ValueError):
    """A native vector packet has unsafe, stale, or inconsistent sources."""


def _read_json(path: Path) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise NativeVectorError(f"Duplicate manifest key: {key}")
            value[key] = item
        return value
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise NativeVectorError("Cannot read native vector manifest") from exc
    if not isinstance(value, dict):
        raise NativeVectorError("Native vector manifest must be an object")
    return value


def _source(root: Path, record: Any, label: str, extensions: set[str]) -> tuple[str, Path, bytes]:
    if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
        raise NativeVectorError(f"{label} needs path and sha256")
    name, digest = record["path"], record["sha256"]
    if not isinstance(name, str) or "\\" in name or not isinstance(digest, str) or not HASH.fullmatch(digest):
        raise NativeVectorError(f"{label} has an unsafe path or digest")
    posix = PurePosixPath(name)
    if posix.is_absolute() or posix.as_posix() != name or any(part in ("", ".", "..") for part in posix.parts) or posix.suffix.lower() not in extensions:
        raise NativeVectorError(f"{label} must be a supported packet-relative file")
    path = root.joinpath(*posix.parts)
    if not path.is_file() or any((root.joinpath(*posix.parts[:index])).is_symlink() for index in range(1, len(posix.parts) + 1)):
        raise NativeVectorError(f"{label} is missing or uses a symlink")
    if not path.resolve().is_relative_to(root.resolve()):
        raise NativeVectorError(f"{label} escapes the packet")
    raw = path.read_bytes()
    if len(raw) > 12 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != digest:
        raise NativeVectorError(f"{label} bytes differ from the manifest")
    return name, path, raw


def _links(svg: bytes, source_name: str) -> tuple[float, float, set[str]]:
    if any(token in svg.lower() for token in (b"<!doctype", b"<!entity", b"<script", b"foreignobject", b"javascript:", b"data:", b"@import", b"url(http:", b"url(https:")):
        raise NativeVectorError("Native SVG must remain passive and local")
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as exc:
        raise NativeVectorError("Native SVG is malformed") from exc
    if root.tag != SVG_TAG:
        raise NativeVectorError("Native vector entry must be SVG")
    dimensions = []
    for key in ("width", "height"):
        match = LENGTH.fullmatch(root.attrib.get(key, ""))
        if not match:
            raise NativeVectorError("Native SVG needs explicit point dimensions")
        dimensions.append(float(match.group(1)))
    links: set[str] = set()
    for element in root.iter():
        href = element.attrib.get("href") or element.attrib.get("{http://www.w3.org/1999/xlink}href")
        if not href or href.startswith("#"):
            continue
        if any(ch in href for ch in ("?", "#", "\\")) or ":" in href or href.startswith("/"):
            raise NativeVectorError("Native SVG has a non-local resource")
        target = posixpath.normpath(posixpath.join(posixpath.dirname(source_name), href))
        if target.startswith("../") or target == ".." or PurePosixPath(target).suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            raise NativeVectorError("Native SVG resource escapes the packet or has an unsupported format")
        links.add(target)
    return dimensions[0], dimensions[1], links


def _render_copy(svg: bytes, source_name: str, dependencies: dict[str, bytes]) -> bytes:
    """Embed exact declared rasters for renderers that block parent-relative links."""
    root = ET.fromstring(svg)
    for element in root.iter():
        for key in ("href", "{http://www.w3.org/1999/xlink}href"):
            href = element.attrib.get(key)
            if not href or href.startswith("#"):
                continue
            target = posixpath.normpath(posixpath.join(posixpath.dirname(source_name), href))
            raw = dependencies[target]
            mime = "image/png" if target.lower().endswith(".png") else "image/jpeg"
            element.set(key, f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def validate_manifest(manifest_path: Path) -> dict[str, Any]:
    data = _read_json(manifest_path)
    if set(data) != {"schema_version", "family_id", "source_state", "outputs"} or data["schema_version"] != "0.1.0":
        raise NativeVectorError("Unsupported native vector manifest")
    if not isinstance(data["family_id"], str) or not ID.fullmatch(data["family_id"]):
        raise NativeVectorError("family_id must be a safe identifier")
    if not isinstance(data["source_state"], str) or data["source_state"] not in {"proposed-unselected", "selected-for-now"}:
        raise NativeVectorError("source_state is unsupported")
    outputs = data["outputs"]
    if not isinstance(outputs, list) or not outputs or len(outputs) > 16:
        raise NativeVectorError("Native vector packet needs one to sixteen outputs")
    root = manifest_path.parent.resolve()
    planned = []
    ids: set[str] = set()
    for index, output in enumerate(outputs):
        if not isinstance(output, dict) or set(output) != {"id", "route", "slot", "context", "page_pt", "entry", "dependencies"}:
            raise NativeVectorError(f"outputs[{index}] has missing or extra fields")
        output_id = output["id"]
        if not isinstance(output_id, str) or not ID.fullmatch(output_id) or output_id in ids:
            raise NativeVectorError("Native vector output IDs must be distinct safe identifiers")
        ids.add(output_id)
        if not isinstance(output["route"], str) or not ID.fullmatch(output["route"]):
            raise NativeVectorError("Each vector output needs its own route key")
        if (output["slot"] is not None and (not isinstance(output["slot"], str) or output["slot"] not in BASELINE)) or output["context"] != "light":
            raise NativeVectorError("Native vector outputs support light document/slick slots or experimental null")
        if data["source_state"] == "proposed-unselected" and output["slot"] is not None:
            raise NativeVectorError("Unselected route outputs cannot claim baseline coverage")
        page = output["page_pt"]
        if not isinstance(page, list) or len(page) != 2 or any(type(n) not in (int, float) or not 100 <= n <= 1500 for n in page):
            raise NativeVectorError("Native vector page_pt must be two point dimensions")
        entry_name, entry_path, svg = _source(root, output["entry"], f"{output_id}.entry", {".svg"})
        width, height, links = _links(svg, entry_name)
        if abs(width - page[0]) > .1 or abs(height - page[1]) > .1:
            raise NativeVectorError("Native SVG dimensions disagree with page_pt")
        deps = output["dependencies"]
        if not isinstance(deps, list):
            raise NativeVectorError("Native vector dependencies must be a list")
        sources = [(entry_name, entry_path, svg)]
        for dep_index, dep in enumerate(deps):
            sources.append(_source(root, dep, f"{output_id}.dependencies[{dep_index}]", {".png", ".jpg", ".jpeg"}))
        declared = {name for name, _, _ in sources[1:]}
        if len(declared) != len(deps) or declared != links:
            raise NativeVectorError(f"{output_id} SVG resource links differ from declared dependencies")
        planned.append({"declaration": output, "sources": sources})
    return {"manifest": data, "outputs": planned, "root": root}


def build(manifest_path: Path, output_dir: Path) -> dict[str, Any]:
    plan = validate_manifest(manifest_path)
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise NativeVectorError("Choose a new output directory for the native vector proof")
    if shutil.which("rsvg-convert") is None:
        raise NativeVectorError("rsvg-convert is required")
    from PIL import Image
    from pypdf import PdfReader

    source_files: dict[str, bytes] = {}
    for item in plan["outputs"]:
        for name, _, raw in item["sources"]:
            key = "source/" + name
            if key in source_files and source_files[key] != raw:
                raise NativeVectorError("Packet sources conflict at the same path")
            source_files[key] = raw
    for name, raw in source_files.items():
        target = output_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    manifest_raw = manifest_path.read_bytes()
    (output_dir / "input-manifest.json").write_bytes(manifest_raw)
    representations = []
    files = dict(source_files)
    raster_ids: dict[str, str] = {}
    for name, raw in source_files.items():
        if Path(name).suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            continue
        with Image.open(output_dir / name) as image:
            image.verify()
        with Image.open(output_dir / name) as image:
            width, height = image.size
            mode = image.mode
        if name.lower().endswith(".png") and raw.startswith(PNG_SIGNATURE) and len(raw) >= 26:
            mode = PNG_COLOR_MODES.get(raw[25])
        raster_id = "raster-" + str(len(raster_ids) + 1)
        raster_ids[name] = raster_id
        representations.append({"id": raster_id, "representation": "raster-source", "path": name,
                                "sha256": hashlib.sha256(raw).hexdigest(), "width": width, "height": height,
                                "color_mode": mode, "master_status": "no-vector-master"})
    report_outputs = []
    for item in plan["outputs"]:
        declaration = item["declaration"]
        output_id = declaration["id"]
        svg_name = "source/" + item["sources"][0][0]
        dep_names = ["source/" + name for name, _, _ in item["sources"][1:]]
        svg_path = output_dir / svg_name
        render_name = f"render-source/{output_id}.svg"
        render_path = output_dir / render_name
        render_path.parent.mkdir(parents=True, exist_ok=True)
        render_bytes = _render_copy(item["sources"][0][2], item["sources"][0][0],
                                    {name: raw for name, _, raw in item["sources"][1:]})
        render_path.write_bytes(render_bytes)
        files[render_name] = render_bytes
        pdf_name = f"pdf/{output_id}.pdf"
        png_name = f"previews/{output_id}.png"
        pdf_path, png_path = output_dir / pdf_name, output_dir / png_name
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        png_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(["rsvg-convert", "--format=pdf", "--output", str(pdf_path), str(render_path)], check=True, capture_output=True, text=True)
            subprocess.run(["rsvg-convert", "--width=1200", "--output", str(png_path), str(render_path)], check=True, capture_output=True, text=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise NativeVectorError(f"Native SVG render failed for {output_id}: {getattr(exc, 'stderr', '')[-1000:]}") from exc
        add_srgb_output_intent(pdf_path)
        pages = PdfReader(str(pdf_path)).pages
        if len(pages) != 1 or any(abs(float(value) - declared) > .5 for value, declared in zip((pages[0].mediabox.width, pages[0].mediabox.height), declaration["page_pt"])):
            raise NativeVectorError(f"{output_id} rendered PDF page differs from its declared geometry")
        with Image.open(png_path) as image:
            if image.format != "PNG":
                raise NativeVectorError("Native vector preview must be PNG")
            image.verify()
        svg_raw, pdf_raw, png_raw = (path.read_bytes() for path in (svg_path, pdf_path, png_path))
        files[pdf_name] = pdf_raw
        representations.append({"id": f"vector-{output_id}", "representation": "vector-master",
                                "path": svg_name, "sha256": hashlib.sha256(svg_raw).hexdigest(),
                                "linked_raster_sources": [raster_ids[name] for name in dep_names], "editable": True})
        source_paths = [svg_name, *dep_names, render_name]
        representations.append({"id": f"pdf-{output_id}", "representation": "derived-export",
                                "path": pdf_name, "sha256": hashlib.sha256(pdf_raw).hexdigest(),
                                "source_paths": source_paths, "generator": "native-vector + librsvg + pypdf",
                                "rendering": "family-owned SVG to sRGB screen PDF", "format": "PDF", "page_count": 1,
                                "page_map": [{"page": 1, "source_paths": source_paths}]})
        report_outputs.append({"id": output_id, "route": declaration["route"], "slot": declaration["slot"],
                               "context": "light", "status": "built-awaiting-visual-review", "page_pt": declaration["page_pt"],
                               "pdf": {"path": pdf_name, "sha256": hashlib.sha256(pdf_raw).hexdigest()},
                               "preview": {"path": png_name, "sha256": hashlib.sha256(png_raw).hexdigest()},
                               "render_copy": {"path": render_name, "sha256": hashlib.sha256(render_bytes).hexdigest(),
                                               "transform": "declared raster links embedded as exact bytes"},
                               "sources": [{"path": name, "sha256": hashlib.sha256(raw).hexdigest()} for name, _, raw in item["sources"]]})
    metadata = {"interface_id": "visual-asset-representations", "interface_version": "0.2.0",
                "schema_version": 1, "representations": representations}
    check = validate_visual_representations(json.dumps(metadata).encode(), files)
    (output_dir / "representations.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    report = {"schema_version": "0.1.0", "family_id": plan["manifest"]["family_id"],
              "source_state": plan["manifest"]["source_state"], "outputs": report_outputs,
              "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
              "coverage": coverage_from_outputs(report_outputs),
              "representation_check": check, "review": "pending", "publication": "not-cleared-by-this-build"}
    (output_dir / "build-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
