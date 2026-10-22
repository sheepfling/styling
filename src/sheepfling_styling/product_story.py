"""Audit connected, image-led product proofs without owning their page design."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from .customer_intake import IntakeError, pinned_file, read_intake
from .family_system import FamilySystemError, audit_family_system

VERSION = "0.1.0"
MM_PER_PT = 25.4 / 72
MEDIA_STATUSES = {"generated-stand-in", "product-screenshot", "product-visualization", "source-illustration"}


class ProductStoryError(ValueError):
    """Product identity, linked views, or stage evidence is inconsistent."""


def _obj(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ProductStoryError(f"{label} must contain exactly {', '.join(sorted(fields))}")
    return value


def _text(value: Any, label: str, limit: int = 500) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ProductStoryError(f"{label} needs bounded non-empty text")
    return value


def _id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", value):
        raise ProductStoryError(f"{label} needs a kebab-case identifier")
    return value


def _pin(root: Path, record: Any, label: str) -> Path:
    try:
        return pinned_file(root, record, label)
    except IntakeError as exc:
        raise ProductStoryError(str(exc)) from exc


def _read(path: Path) -> dict[str, Any]:
    try:
        return read_intake(path)
    except IntakeError as exc:
        raise ProductStoryError(str(exc)) from exc


def _initials(backronym: str) -> str:
    return "".join(word[0].upper() for word in re.findall(r"[A-Za-z]+", backronym)
                   if word.lower() not in {"and", "of", "the", "for", "in", "a", "an", "to"})


def _rect(value: Any, page_mm: list[float], label: str) -> tuple[float, float, float, float]:
    _obj(value, {"x_mm", "y_mm", "width_mm", "height_mm"}, label)
    numbers = [value[key] for key in ("x_mm", "y_mm", "width_mm", "height_mm")]
    if any(type(number) not in (int, float) or not 0 <= number <= 500 for number in numbers):
        raise ProductStoryError(f"{label} needs bounded millimeter geometry")
    x, y, width, height = map(float, numbers)
    if width < 1 or height < 1 or x + width > page_mm[0] + .7 or y + height > page_mm[1] + .7:
        raise ProductStoryError(f"{label} lies outside the proof page")
    return x, y, width, height


def _overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return min(a[0] + a[2], b[0] + b[2]) > max(a[0], b[0]) + .01 and min(a[1] + a[3], b[1] + b[3]) > max(a[1], b[1]) + .01


def _stage(media: dict[str, Any], page_mm: list[float], asset: dict[str, Any]) -> dict[str, Any]:
    stage = _obj(media["stage"], {"page", "panel", "inset_mm", "caption_box"}, "media.stage")
    panel = _rect(stage["panel"], page_mm, "media.stage.panel")
    caption_box = _rect(stage["caption_box"], page_mm, "media.stage.caption_box")
    if _overlap(panel, caption_box):
        raise ProductStoryError("Media caption overlaps its protected image panel")
    inset = stage["inset_mm"]
    if type(inset) not in (int, float) or not 0 <= inset <= 30 or 2 * inset >= min(panel[2], panel[3]):
        raise ProductStoryError("Media inset does not leave a positive image area")
    inner_width, inner_height = panel[2] - 2 * inset, panel[3] - 2 * inset
    ratio = asset["width_px"] / asset["height_px"]
    placed_width = min(inner_width, inner_height * ratio)
    placed_height = placed_width / ratio
    return {"page": stage["page"], "panel_mm": list(panel), "caption_box_mm": list(caption_box),
            "inset_mm": float(inset), "contained_image_mm": [round(placed_width, 3), round(placed_height, 3)]}


def audit_product_story(manifest_path: Path) -> dict[str, Any]:
    """Bind product identity, media stages, and cross-product links to exact proofs."""
    manifest = _read(manifest_path)
    _obj(manifest, {"schema_version", "family_system", "products"}, "product story")
    if manifest["schema_version"] != VERSION:
        raise ProductStoryError("Unsupported product-story schema version")
    family_path = _pin(manifest_path.parent, manifest["family_system"], "family_system")
    try:
        family = audit_family_system(family_path)
    except FamilySystemError as exc:
        raise ProductStoryError(f"Family proof audit: {exc}") from exc
    outputs = {item["key"]: item for item in family["outputs"]}
    products = manifest["products"]
    if not isinstance(products, list) or not products or len(products) > 32:
        raise ProductStoryError("Product story needs one to 32 products")
    ids: set[str] = set()
    sequences: set[int] = set()
    rows = []
    for product in products:
        _obj(product, {"id", "proof", "identity", "media", "facets", "links"}, "product")
        product_id = _id(product["id"], "product.id")
        if product_id in ids:
            raise ProductStoryError("Product IDs must be distinct")
        ids.add(product_id)
        proof_key = _text(product["proof"], "product.proof", 180)
        proof = outputs.get(proof_key)
        if proof is None or proof["source_kind"] != "composition-recipe" or proof["pdf"] is None:
            raise ProductStoryError("Product proof must name a recipe PDF in the audited family")
        if proof["page_count"] != 2 or proof.get("duplex") is None:
            raise ProductStoryError("Product proof needs front/back duplex intent")
        identity = _obj(product["identity"], {"name", "backronym", "descriptor", "sequence"}, "identity")
        name = _text(identity["name"], "identity.name", 30)
        backronym = _text(identity["backronym"], "identity.backronym", 180)
        descriptor = _text(identity["descriptor"], "identity.descriptor", 180)
        if not re.fullmatch(r"[A-Z]{3,12}", name) or _initials(backronym) != name:
            raise ProductStoryError("Product backronym initials must spell its name")
        sequence = identity["sequence"]
        if type(sequence) is not int or not 1 <= sequence <= 32 or sequence in sequences:
            raise ProductStoryError("Product sequence must be a distinct positive integer")
        sequences.add(sequence)
        build_root = (family_path.parent / proof["build_report"]["path"]).parent
        if proof.get("content") is None:
            raise ProductStoryError("Product proof needs a pinned native content record")
        content = _read(_pin(build_root, proof["content"], "product.content"))
        for key, expected in (("identity_name", name), ("identity_backronym", backronym),
                              ("identity_descriptor", descriptor), ("identity_suite_index", f"{sequence:02d}")):
            if content.get(key) != expected:
                raise ProductStoryError(f"Product identity differs from native content field {key}")
        pdf_path = _pin(build_root, proof["pdf"], "product.pdf")
        pdf_text = " ".join(" ".join((page.extract_text() or "").split()) for page in PdfReader(str(pdf_path)).pages)
        for label in (name, backronym, descriptor):
            if " ".join(label.split()) not in pdf_text:
                raise ProductStoryError("Product identity is absent from extracted PDF text")
        assets = {(item["path"], item["sha256"]): item for item in proof.get("assets", [])}
        media = product["media"]
        if not isinstance(media, list) or not media or len(media) > 12 or len(assets) != len(media):
            raise ProductStoryError("Media slots must account for every raster asset in the product proof")
        media_ids: set[str] = set()
        used_assets: set[tuple[str, str]] = set()
        stage_rows = []
        page_panels: dict[int, list[tuple[float, float, float, float]]] = {1: [], 2: []}
        page_captions: dict[int, list[tuple[float, float, float, float]]] = {1: [], 2: []}
        for item in media:
            _obj(item, {"id", "asset", "status", "status_label", "fit", "caption",
                        "caption_field", "status_field", "stage"}, "media")
            media_id = _id(item["id"], "media.id")
            if media_id in media_ids:
                raise ProductStoryError("Media IDs must be distinct")
            media_ids.add(media_id)
            asset_pin = _obj(item["asset"], {"path", "sha256"}, "media.asset")
            asset_key = (asset_pin["path"], asset_pin["sha256"])
            asset = assets.get(asset_key)
            if asset is None or item["status"] not in MEDIA_STATUSES or item["fit"] != "contain":
                raise ProductStoryError("Media must bind an exact proof asset with supported status and contain fit")
            if asset_key in used_assets:
                raise ProductStoryError("A proof asset cannot fill two declared media slots")
            used_assets.add(asset_key)
            caption = _text(item["caption"], "media.caption", 240)
            status_label = _text(item["status_label"], "media.status_label", 80)
            caption_field = _text(item["caption_field"], "media.caption_field", 100)
            status_field = _text(item["status_field"], "media.status_field", 100)
            if content.get(caption_field) != caption or content.get(status_field) != status_label:
                raise ProductStoryError("Media caption or provenance label differs from native content")
            if caption not in pdf_text or status_label not in pdf_text:
                raise ProductStoryError("Media caption or provenance label is absent from the PDF")
            page = item["stage"].get("page") if isinstance(item["stage"], dict) else None
            if type(page) is not int or page not in (1, 2):
                raise ProductStoryError("Media stage must name front or back page")
            page_mm = [dimension * MM_PER_PT for dimension in proof["page_sizes_pt"][page - 1]]
            placed = _stage(item, page_mm, asset)
            panel = tuple(placed["panel_mm"])
            if any(_overlap(panel, other) for other in page_panels[page]):
                raise ProductStoryError("Two media panels overlap on the same face")
            page_panels[page].append(panel)
            page_captions[page].append(tuple(placed["caption_box_mm"]))
            stage_rows.append({"id": media_id, "asset": asset_pin,
                               "status": item["status"], "caption": caption, "fit": "contain"} | placed)
        for page in (1, 2):
            for index, caption in enumerate(page_captions[page]):
                if any(_overlap(caption, panel) for panel in page_panels[page]):
                    raise ProductStoryError("A media caption overlaps a protected image panel")
                if any(_overlap(caption, other) for other in page_captions[page][index + 1:]):
                    raise ProductStoryError("Two media captions overlap on the same face")
        facets = product["facets"]
        if not isinstance(facets, list) or not facets or len(facets) > 24:
            raise ProductStoryError("Product needs bounded concept facets")
        facet_ids: set[str] = set()
        for facet in facets:
            _obj(facet, {"id", "label", "evidence_field", "media"}, "facet")
            facet_id = _id(facet["id"], "facet.id")
            if facet_id in facet_ids:
                raise ProductStoryError("Facet IDs must be distinct")
            facet_ids.add(facet_id)
            _text(facet["label"], "facet.label", 120)
            field = _text(facet["evidence_field"], "facet.evidence_field", 100)
            if not isinstance(content.get(field), str) or not content[field].strip():
                raise ProductStoryError("Facet evidence field is absent from native content")
            if not isinstance(facet["media"], list) or not facet["media"] or any(media_id not in media_ids for media_id in facet["media"]):
                raise ProductStoryError("Facet must reference current media stages")
            if len(set(facet["media"])) != len(facet["media"]):
                raise ProductStoryError("Facet media IDs must be distinct")
        links = product["links"]
        if not isinstance(links, list) or len(links) > 16:
            raise ProductStoryError("Product links must be a bounded list")
        for link in links:
            _obj(link, {"to", "relationship"}, "product link")
            _id(link["to"], "product link target")
            _text(link["relationship"], "product link relationship", 160)
            if link["to"] == product_id:
                raise ProductStoryError("A product cannot link to itself")
        rows.append({"id": product_id, "proof": proof_key, "identity": identity,
                     "duplex": proof["duplex"], "media": stage_rows,
                     "facets": facets, "links": links, "context": proof["context"],
                     "review": "pending"})
    for row in rows:
        targets = [link["to"] for link in row["links"]]
        if len(set(targets)) != len(targets) or any(target not in ids for target in targets):
            raise ProductStoryError("Product links need distinct targets in the same suite")
    return {"schema_version": VERSION, "family_id": family["family_id"],
            "family_system_sha256": manifest["family_system"]["sha256"],
            "products": sorted(rows, key=lambda item: item["identity"]["sequence"]),
            "review": "pending", "print": "pending", "claims": "unverified-by-this-audit"}
