"""Assemble distinct native and recipe proofs into one family-level review map.

This layer verifies evidence and routes; it never substitutes a visual template or
promotes a proof to an approved customer deliverable.
"""
from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Any

from .customer_intake import IntakeError, pinned_file, read_intake
from .family_coverage import BASELINE_SLOTS, coverage_from_outputs
from .visual_representations import RepresentationError, validate_visual_representations

VERSION = "0.1.0"
KINDS = {"native-tex", "native-vector", "composition-recipe"}
STATES = {"proposed-unselected", "selected-for-now"}


class FamilySystemError(ValueError):
    """A family assembly or one of its pinned build packets is inconsistent."""


def _object(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise FamilySystemError(f"{label} must declare exactly {', '.join(sorted(fields))}")
    return value


def _identifier(value: Any, label: str) -> str:
    if (not isinstance(value, str) or not value or len(value) > 80
            or not value[0].islower() or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in value)
            or "--" in value or value.endswith("-")):
        raise FamilySystemError(f"{label} must be a kebab-case identifier")
    return value


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return read_intake(path)
    except IntakeError as exc:
        raise FamilySystemError(str(exc)) from exc


def _pin(root: Path, record: Any, label: str) -> Path:
    try:
        return pinned_file(root, record, label)
    except IntakeError as exc:
        raise FamilySystemError(str(exc)) from exc


def _packet_file(root: Path, relative: Any) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise FamilySystemError("Packet file path must be a safe relative path")
    posix = PurePosixPath(relative)
    if posix.is_absolute() or any(part in {"", ".", ".."} for part in relative.split("/")):
        raise FamilySystemError("Packet file escapes its build directory")
    path = root.joinpath(*posix.parts)
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise FamilySystemError(f"Packet file is missing: {relative}")
    for part in (path, *path.parents):
        if part == root:
            break
        if part.is_symlink():
            raise FamilySystemError(f"Packet file uses a symlink: {relative}")
    return path


def _verify_representations(root: Path, report: dict[str, Any]) -> None:
    path = _packet_file(root, "representations.json")
    metadata = _read_json(path)
    representations = metadata.get("representations")
    if not isinstance(representations, list):
        raise FamilySystemError("Build packet has no visual representations")
    paths: set[str] = set()
    for item in representations:
        if not isinstance(item, dict):
            raise FamilySystemError("Build packet has malformed visual representations")
        if not isinstance(item.get("source_paths", []), list) or not isinstance(item.get("page_map", []), list):
            raise FamilySystemError("Build packet has malformed representation links")
        paths.add(item.get("path"))
        paths.update(item.get("source_paths", []))
        for page in item.get("page_map", []):
            if not isinstance(page, dict) or not isinstance(page.get("source_paths", []), list):
                raise FamilySystemError("Build packet has malformed page source links")
            paths.update(page.get("source_paths", []))
    files = {name: _packet_file(root, name).read_bytes() for name in paths}
    try:
        result = validate_visual_representations(path.read_bytes(), files)
    except RepresentationError as exc:
        raise FamilySystemError(f"Visual representations: {exc}") from exc
    original = report.get("representation_check", report.get("representation_checks"))
    if result != original:
        raise FamilySystemError("Current visual representations differ from build evidence")


def _verify_native_sources(root: Path, report: dict[str, Any], kind: str) -> dict[str, Any]:
    path = _packet_file(root, "input-manifest.json")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != report.get("manifest_sha256"):
        raise FamilySystemError("Native input manifest differs from build evidence")
    manifest = _read_json(path)
    if manifest.get("family_id") != report.get("family_id") or manifest.get("source_state") != report.get("source_state"):
        raise FamilySystemError("Native manifest family or route state differs from build report")
    if kind == "native-tex":
        sources = manifest.get("sources")
        if not isinstance(sources, list) or not sources:
            raise FamilySystemError("Native TeX source list is missing")
    else:
        outputs = manifest.get("outputs")
        if not isinstance(outputs, list) or any(not isinstance(output, dict) or not isinstance(output.get("dependencies"), list) for output in outputs):
            raise FamilySystemError("Native SVG output list is missing")
        sources = [pin for output in outputs for pin in [output.get("entry"), *output.get("dependencies", [])]]
    for index, source in enumerate(sources):
        if not isinstance(source, dict) or set(source) != {"path", "sha256"}:
            raise FamilySystemError("Native source pin is malformed")
        _pin(root, {"path": "source/" + source["path"], "sha256": source["sha256"]}, f"native.sources[{index}]")
    return manifest


def _verify_pdf_and_previews(root: Path, pdf: Any, previews: Any, page_count: Any,
                             page_pt: Any) -> list[list[float]]:
    from PIL import Image
    from pypdf import PdfReader

    path = _pin(root, pdf, "output.pdf")
    if path.suffix.lower() != ".pdf" or not isinstance(previews, list) or not previews:
        raise FamilySystemError("Each PDF output needs pinned page previews")
    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        raise FamilySystemError("Output PDF cannot be read") from exc
    if type(page_count) is not int or page_count < 1 or len(reader.pages) != page_count or len(previews) != page_count:
        raise FamilySystemError("PDF and preview page counts differ from build evidence")
    page_sizes = [[float(page.mediabox.width), float(page.mediabox.height)] for page in reader.pages]
    if page_pt is not None:
        if (not isinstance(page_pt, list) or len(page_pt) != 2
                or any(type(value) not in (int, float) for value in page_pt)):
            raise FamilySystemError("PDF point geometry is malformed")
        for size in page_sizes:
            if abs(size[0] - page_pt[0]) > .6 or abs(size[1] - page_pt[1]) > .6:
                raise FamilySystemError("PDF page dimensions differ from build evidence")
    for index, pin in enumerate(previews):
        preview = _pin(root, pin, f"output.preview[{index}]")
        try:
            with Image.open(preview) as image:
                if image.format != "PNG":
                    raise FamilySystemError("Page preview is not PNG")
                image.verify()
        except OSError as exc:
            raise FamilySystemError("Page preview cannot be read") from exc
    return page_sizes


def _duplex(value: Any, page_count: int) -> dict[str, Any] | None:
    if value is None:
        return None
    if (not isinstance(value, dict) or value.get("schema_version") != "0.1.0" or page_count != 2
            or value.get("flip") not in {"long-edge", "short-edge"}
            or value.get("front_page") != 1 or value.get("back_page") != 2
            or value.get("sheet_count") != 1 or value.get("imposition") != "none"
            or value.get("physical_print_review") != "pending"
            or value.get("page_faces") != [{"page": 1, "sheet": 1, "face": "front"},
                                           {"page": 2, "sheet": 1, "face": "back"}]):
        raise FamilySystemError("Duplex proof needs two upright faces and pending print review")
    return {"flip": value["flip"], "front_page": 1, "back_page": 2,
            "physical_print_review": "pending"}


def _native_outputs(root: Path, report: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    manifest = _verify_native_sources(root, report, kind)
    declared = manifest.get("outputs")
    actual = report.get("outputs")
    if not isinstance(declared, list) or not isinstance(actual, list) or len(declared) != len(actual):
        raise FamilySystemError("Native output declarations differ from build report")
    by_id = {item.get("id"): item for item in declared}
    if len(by_id) != len(declared):
        raise FamilySystemError("Native output IDs must be distinct")
    normalized = []
    seen_ids = set()
    for item in actual:
        if (not isinstance(item, dict) or item.get("id") not in by_id or item.get("id") in seen_ids
                or item.get("status") != "built-awaiting-visual-review"):
            raise FamilySystemError("Native build output is incomplete or undeclared")
        seen_ids.add(item["id"])
        source = by_id[item["id"]]
        for field in ("slot", "context", "page_pt"):
            if item.get(field) != source.get(field):
                raise FamilySystemError(f"Native {item['id']} {field} differs from source declaration")
        route = source["route"] if kind == "native-vector" else manifest["route"]
        if kind == "native-vector" and item.get("route") != route:
            raise FamilySystemError("Native SVG route differs from source declaration")
        count = source.get("page_count", 1)
        previews = item.get("previews", [item.get("preview")])
        page_sizes = _verify_pdf_and_previews(root, item.get("pdf"), previews, count, source["page_pt"])
        normalized.append({"id": item["id"], "route": route, "slot": item["slot"],
                           "context": item["context"], "pdf": item["pdf"], "previews": previews,
                           "page_count": count, "page_sizes_pt": page_sizes,
                           "duplex": None, "assets": [], "content": None})
    expected = coverage_from_outputs(actual)
    if kind == "native-tex" and manifest.get("web_source") is not None:
        expected["web-light"] = {"status": "source-only", "outputs": []}
    if report.get("coverage") != expected or report.get("review") != "pending":
        raise FamilySystemError("Native coverage or review state differs from actual outputs")
    _verify_representations(root, report)
    return normalized


def _recipe_outputs(root: Path, report: dict[str, Any], route: str) -> list[dict[str, Any]]:
    if report.get("status") != "checks-passed-awaiting-visual-review" or report.get("visual_review") != "pending":
        raise FamilySystemError("Composition recipe has not completed its proof checks")
    pdfs, previews = report.get("pdfs"), report.get("previews")
    if not isinstance(pdfs, dict) or not pdfs or not isinstance(previews, dict):
        raise FamilySystemError("Composition recipe has no PDF proof outputs")
    normalized = []
    metadata = _read_json(_packet_file(root, "representations.json"))
    records = metadata.get("representations")
    if not isinstance(records, list):
        raise FamilySystemError("Recipe has no visual representation records")
    raster_records = {(item.get("path"), item.get("sha256")) for item in records
                      if isinstance(item, dict) and item.get("representation") == "raster-source"}
    for output_id, pdf in pdfs.items():
        if not isinstance(pdf, dict) or pdf.get("visual_review") != "pending":
            raise FamilySystemError("Recipe PDF visual review state is invalid")
        if output_id not in previews:
            raise FamilySystemError("Recipe PDF has no page previews")
        pin = {"path": pdf.get("path"), "sha256": pdf.get("sha256")}
        pages = pdf.get("checks", {}).get("page_count")
        if not isinstance(pages, int):
            pages = len(previews[output_id])
        page_sizes = _verify_pdf_and_previews(root, pin, previews[output_id], pages, None)
        duplex = _duplex(pdf.get("duplex"), pages)
        assets = []
        asset_paths = set()
        for index, asset in enumerate(report.get("assets", {}).get(output_id, [])):
            if not isinstance(asset, dict):
                raise FamilySystemError("Recipe media asset record is malformed")
            asset_pin = {"path": asset.get("path"), "sha256": asset.get("sha256")}
            asset_path = _pin(root, asset_pin, f"recipe.assets[{output_id}][{index}]")
            if (asset_pin["path"], asset_pin["sha256"]) not in raster_records or asset_pin["path"] in asset_paths:
                raise FamilySystemError("Recipe media asset differs from visual representation evidence")
            asset_paths.add(asset_pin["path"])
            if any(type(asset.get(key)) is not int or asset[key] < 1 for key in ("width", "height")):
                raise FamilySystemError("Recipe media dimensions are malformed")
            from PIL import Image
            try:
                with Image.open(asset_path) as image:
                    if image.size != (asset["width"], asset["height"]):
                        raise FamilySystemError("Recipe media dimensions differ from source pixels")
            except OSError as exc:
                raise FamilySystemError("Recipe media asset is not a readable image") from exc
            assets.append(asset_pin | {"width_px": asset["width"], "height_px": asset["height"]})
        content_path = f"editable-source/{output_id}/content.json"
        content_digest = pdf.get("source_hashes", {}).get(content_path)
        content = {"path": content_path, "sha256": content_digest} if content_digest else None
        if content is not None:
            _pin(root, content, f"recipe.content[{output_id}]")
        normalized.append({"id": output_id, "route": route, "slot": pdf.get("slot"),
                           "context": pdf.get("context"), "pdf": pin,
                           "previews": previews[output_id], "page_count": pages,
                           "page_sizes_pt": page_sizes, "duplex": duplex,
                           "assets": assets, "content": content})
    coverage = coverage_from_outputs(normalized)
    web = report.get("web", {})
    if web.get("status") == "static-checks-passed-awaiting-browser-review" and web.get("context") == "light":
        coverage["web-light"] = {"status": "static-checks-passed-awaiting-browser-review",
                                 "outputs": [web["id"]]}
    if report.get("coverage") != coverage:
        raise FamilySystemError("Recipe coverage differs from its PDF and web proofs")
    if web.get("status") == "static-checks-passed-awaiting-browser-review":
        sources = web.get("sources")
        if not isinstance(sources, list) or not sources:
            raise FamilySystemError("Recipe web proof has no pinned sources")
        for index, source in enumerate(sources):
            _pin(root, {"path": source.get("path"), "sha256": source.get("sha256")}, f"web.sources[{index}]")
        _pin(root, web.get("representation_metadata"), "web.representation_metadata")
        if web.get("context") == "light":
            entry_source = next((item for item in sources if item["path"] == web.get("entry")), None)
            if entry_source is None:
                raise FamilySystemError("Recipe web entry is absent from pinned sources")
            normalized.append({"id": web["id"], "route": route, "slot": "web-light",
                               "context": "light", "pdf": None, "previews": [], "page_count": 0,
                               "page_sizes_pt": [], "duplex": None, "assets": [], "content": None,
                               "source": {"path": web["entry"], "sha256": entry_source["sha256"]}})
    _verify_representations(root, report)
    return normalized


def audit_family_system(manifest_path: Path) -> dict[str, Any]:
    """Verify build packets and emit route-specific, review-pending coverage."""
    manifest = _read_json(manifest_path)
    _object(manifest, {"schema_version", "family_id", "routes", "builds"}, "family system")
    if manifest["schema_version"] != VERSION:
        raise FamilySystemError("Unsupported family-system schema version")
    family_id = _identifier(manifest["family_id"], "family_id")
    routes = manifest["routes"]
    builds = manifest["builds"]
    if not isinstance(routes, list) or not routes or len(routes) > 24 or not isinstance(builds, list) or not builds or len(builds) > 24:
        raise FamilySystemError("Family system needs bounded routes and builds")
    route_map = {}
    for route in routes:
        _object(route, {"id", "state", "signature_features"}, "route")
        route_id = _identifier(route["id"], "route.id")
        if route_id in route_map or route["state"] not in STATES:
            raise FamilySystemError("Routes must have distinct IDs and supported states")
        features = route["signature_features"]
        if not isinstance(features, list) or not features or len(features) > 32:
            raise FamilySystemError("Every route needs signature features for visual review")
        feature_ids = set()
        for feature in features:
            _object(feature, {"id", "description", "outputs"}, "signature feature")
            name = _identifier(feature["id"], "signature feature.id")
            if name in feature_ids or not isinstance(feature["description"], str) or not feature["description"].strip() or len(feature["description"]) > 500:
                raise FamilySystemError("Signature features need distinct IDs and bounded descriptions")
            if (not isinstance(feature["outputs"], list) or not feature["outputs"]
                    or any(not isinstance(value, str) for value in feature["outputs"])
                    or len(set(feature["outputs"])) != len(feature["outputs"])):
                raise FamilySystemError("Signature features need distinct output IDs")
            for output_id in feature["outputs"]:
                _identifier(output_id, "signature feature output")
            feature_ids.add(name)
        route_map[route_id] = route

    normalized = []
    build_refs = []
    seen = set()
    source_only_web = False
    for index, build in enumerate(builds):
        _object(build, {"kind", "route", "source_family_id", "report"}, f"builds[{index}]")
        kind = build["kind"]
        if kind not in KINDS or (kind == "composition-recipe") != (build["route"] is not None):
            raise FamilySystemError("Build kind and explicit recipe route disagree")
        route = _identifier(build["route"], "build.route") if build["route"] is not None else None
        if route is not None and route not in route_map:
            raise FamilySystemError("Build references an undeclared route")
        source_family_id = _identifier(build["source_family_id"], "build.source_family_id")
        report_path = _pin(manifest_path.parent, build["report"], f"builds[{index}].report")
        report = _read_json(report_path)
        if report.get("family_id") != source_family_id:
            raise FamilySystemError("Build report differs from its explicit source family ID")
        root = report_path.parent
        rows = _recipe_outputs(root, report, route) if kind == "composition-recipe" else _native_outputs(root, report, kind)
        if kind == "native-tex" and report.get("web_source") is not None:
            source_only_web = True
        for row in rows:
            if row["route"] not in route_map:
                raise FamilySystemError("Build output references an undeclared route")
            if kind != "composition-recipe" and report.get("source_state") != route_map[row["route"]]["state"]:
                raise FamilySystemError("Route selection differs from native source state")
            key = (row["route"], row["id"])
            if key in seen:
                raise FamilySystemError("A route cannot claim the same output twice")
            seen.add(key)
            if row["slot"] is not None and row["slot"] not in BASELINE_SLOTS:
                raise FamilySystemError("Output claims an unknown baseline slot")
            if route_map[row["route"]]["state"] == "proposed-unselected" and row["slot"] is not None:
                raise FamilySystemError("Unselected route cannot claim baseline coverage")
            normalized.append(row | {"source_kind": kind, "key": row["route"] + "/" + row["id"],
                                     "build_report": build["report"]})
        build_refs.append({"kind": kind, "source_family_id": source_family_id,
                           "report_sha256": build["report"]["sha256"]})

    output_keys = {(item["route"], item["id"]) for item in normalized}
    review = {}
    for route_id, route in route_map.items():
        for feature in route["signature_features"]:
            if any((route_id, output_id) not in output_keys for output_id in feature["outputs"]):
                raise FamilySystemError("Signature feature names an output absent from its route")
        for item in (output for output in normalized if output["route"] == route_id):
            applicable = [feature["id"] for feature in route["signature_features"] if item["id"] in feature["outputs"]]
            if not applicable:
                raise FamilySystemError("Every output needs a route-specific visual signature to review")
            review[item["key"]] = applicable

    coverage = {}
    for slot in BASELINE_SLOTS:
        matching = [item["key"] for item in normalized if item["slot"] == slot and item["context"] == "light"]
        status = ("static-checks-passed-awaiting-browser-review" if slot == "web-light" and matching
                  else "built-awaiting-visual-review" if matching else "source-only" if slot == "web-light" and source_only_web else "not-run")
        coverage[slot] = {"status": status,
                          "outputs": matching}
    return {"schema_version": VERSION, "family_id": family_id,
            "routes": [{"id": route["id"], "state": route["state"],
                        "signature_features": route["signature_features"],
                        "outputs": [item["key"] for item in normalized if item["route"] == route["id"]]}
                       for route in routes],
            "builds": build_refs, "outputs": normalized, "coverage": coverage,
            "review_checklist": review, "review": "pending", "publication": "not-cleared-by-this-audit"}
