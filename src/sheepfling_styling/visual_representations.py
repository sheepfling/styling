"""Validate explicit vector, raster, and derived visual provenance."""
from __future__ import annotations

import hashlib
import json
import posixpath
import struct
import xml.etree.ElementTree as ET
from pathlib import PurePosixPath
from typing import Any


class RepresentationError(ValueError):
    """A visual-representation or output-index record is inconsistent."""


REPRESENTATION_KINDS = {"vector-master", "raster-source", "derived-export"}
OUTPUT_STATUSES = {"current_proof", "historical_proof", "not_available_current", "not_applicable"}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_COLOR_MODES = {0: "Grayscale", 2: "RGB", 3: "Indexed", 4: "Grayscale with alpha", 6: "RGBA"}


def _safe_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise RepresentationError("{} must be a non-empty POSIX relative path".format(label))
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise RepresentationError("{} must stay within the family packet".format(label))
    return path.as_posix()


def _load_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RepresentationError("{} is not readable JSON".format(label)) from exc
    if not isinstance(result, dict):
        raise RepresentationError("{} must be a JSON object".format(label))
    return result


def validate_representation_contract(contract_bytes: bytes) -> dict[str, Any]:
    """Check the declared metadata contract against the installed validator."""
    contract = _load_object(contract_bytes, "visual representation contract")
    if contract.get("interface_id") != "visual-asset-representations" or contract.get("interface_version") != "0.1.0":
        raise RepresentationError("Unsupported visual representation contract")
    declared = contract.get("representation_kinds")
    if not isinstance(declared, list) or set(declared) != REPRESENTATION_KINDS:
        raise RepresentationError("Visual representation kinds differ from the installed contract")
    expected_fields = {
        "vector-master": {"id", "path", "sha256", "linked_raster_sources", "editable"},
        "raster-source": {"id", "path", "sha256", "width", "height", "color_mode", "master_status"},
        "derived-export": {"id", "path", "sha256", "source_paths", "generator", "rendering", "format", "page_count", "page_map"},
    }
    required_fields = contract.get("required_fields")
    if not isinstance(required_fields, dict) or set(required_fields) != REPRESENTATION_KINDS:
        raise RepresentationError("Visual representation required fields differ from the installed contract")
    for kind, fields in expected_fields.items():
        declared_fields = required_fields.get(kind)
        if not isinstance(declared_fields, list) or set(declared_fields) != fields:
            raise RepresentationError("Visual representation required fields differ for {}".format(kind))
    return {"status": "passed", "representation_kinds": sorted(REPRESENTATION_KINDS)}


def _check_file(record: dict[str, Any], files: dict[str, bytes], label: str) -> tuple[str, bytes]:
    path = _safe_path(record.get("path"), label + " path")
    raw = files.get(path)
    if raw is None:
        raise RepresentationError("{} refers to missing packet file {}".format(label, path))
    digest = record.get("sha256")
    if not isinstance(digest, str) or len(digest) != 64 or hashlib.sha256(raw).hexdigest() != digest:
        raise RepresentationError("{} digest does not match {}".format(label, path))
    return path, raw


def validate_visual_representations(
    metadata_bytes: bytes,
    files: dict[str, bytes],
) -> dict[str, Any]:
    """Validate representation metadata against the exact files in a packet."""
    document = _load_object(metadata_bytes, "visual representation metadata")
    if document.get("schema_version") != 1:
        raise RepresentationError("Unsupported visual representation schema version")
    if document.get("interface_id") != "visual-asset-representations" or document.get("interface_version") != "0.1.0":
        raise RepresentationError("Unsupported visual representation contract")
    representations = document.get("representations")
    if not isinstance(representations, list) or not representations:
        raise RepresentationError("Visual representation metadata must contain records")

    ids: set[str] = set()
    raster_paths: dict[str, str] = {}
    for record in representations:
        if isinstance(record, dict) and record.get("representation") == "raster-source":
            record_id = record.get("id")
            if not isinstance(record_id, str) or not record_id:
                raise RepresentationError("Raster-source ids must be non-empty strings")
            raster_paths[record_id] = _safe_path(record.get("path"), "raster-source path")
    for index, record in enumerate(representations):
        label = "representations[{}]".format(index)
        if not isinstance(record, dict):
            raise RepresentationError("{} must be an object".format(label))
        record_id = record.get("id")
        kind = record.get("representation")
        if not isinstance(record_id, str) or not record_id or record_id in ids:
            raise RepresentationError("{} id must be unique and non-empty".format(label))
        ids.add(record_id)
        if kind not in REPRESENTATION_KINDS:
            raise RepresentationError("{} has an unsupported representation kind".format(label))
        path, raw = _check_file(record, files, label)

        if kind == "raster-source":
            if len(raw) < 26 or raw[:8] != PNG_SIGNATURE or raw[12:16] != b"IHDR":
                raise RepresentationError("{} is not a readable PNG raster source".format(label))
            width, height = struct.unpack(">II", raw[16:24])
            color_mode = PNG_COLOR_MODES.get(raw[25])
            if (record.get("width"), record.get("height"), record.get("color_mode")) != (width, height, color_mode):
                raise RepresentationError("{} PNG dimensions or color mode differ from the metadata".format(label))
            if record.get("master_status") not in ("no-vector-master", "vector-master-available"):
                raise RepresentationError("{} must state whether a vector master exists".format(label))
            raster_paths[record_id] = path

        elif kind == "vector-master":
            if not path.lower().endswith(".svg") or record.get("editable") is not True:
                raise RepresentationError("{} must reference an editable SVG source".format(label))
            try:
                tree = ET.fromstring(raw)
            except ET.ParseError as exc:
                raise RepresentationError("{} SVG source is malformed".format(label)) from exc
            linked_ids = record.get("linked_raster_sources")
            if not isinstance(linked_ids, list) or not all(isinstance(item, str) for item in linked_ids):
                raise RepresentationError("{} must list linked raster sources".format(label))
            hrefs = []
            for element in tree.iter():
                href = element.attrib.get("href") or element.attrib.get("{http://www.w3.org/1999/xlink}href")
                if href and not href.startswith(("data:", "#")):
                    hrefs.append(posixpath.normpath(posixpath.join(posixpath.dirname(path), href)))
            expected_paths = {raster_paths[item] for item in linked_ids if item in raster_paths}
            if len(expected_paths) != len(linked_ids) or set(hrefs) != expected_paths:
                raise RepresentationError("{} SVG raster links do not match its declared raster sources".format(label))

        else:
            if not path.lower().endswith(".pdf") or not raw.startswith(b"%PDF-"):
                raise RepresentationError("{} must reference a PDF derived export".format(label))
            source_paths = record.get("source_paths")
            if not isinstance(source_paths, list) or not source_paths:
                raise RepresentationError("{} must list source files".format(label))
            normalized = [_safe_path(item, label + " source path") for item in source_paths]
            if any(item not in files for item in normalized):
                raise RepresentationError("{} names a missing source file".format(label))
            if not isinstance(record.get("generator"), str) or not record["generator"]:
                raise RepresentationError("{} must name its generator".format(label))
            if not isinstance(record.get("rendering"), str) or not record["rendering"]:
                raise RepresentationError("{} must describe its rendering".format(label))
            if record.get("format") != "PDF":
                raise RepresentationError("{} output format must be PDF".format(label))
            page_count = record.get("page_count")
            page_map = record.get("page_map")
            if not isinstance(page_count, int) or isinstance(page_count, bool) or page_count < 1:
                raise RepresentationError("{} must declare a positive page count".format(label))
            if not isinstance(page_map, list) or len(page_map) != page_count:
                raise RepresentationError("{} page map must cover every PDF page".format(label))
            page_numbers = set()
            for page_entry in page_map:
                if not isinstance(page_entry, dict):
                    raise RepresentationError("{} page map entries must be objects".format(label))
                page_number = page_entry.get("page")
                page_sources = page_entry.get("source_paths")
                if not isinstance(page_number, int) or isinstance(page_number, bool) or not 1 <= page_number <= page_count or page_number in page_numbers:
                    raise RepresentationError("{} page map contains a duplicate or invalid page".format(label))
                if not isinstance(page_sources, list) or not page_sources:
                    raise RepresentationError("{} page map must name each page's source files".format(label))
                normalized_sources = [_safe_path(item, label + " page source path") for item in page_sources]
                if any(item not in files for item in normalized_sources):
                    raise RepresentationError("{} page map names a missing source file".format(label))
                page_numbers.add(page_number)
            if page_numbers != set(range(1, page_count + 1)):
                raise RepresentationError("{} page map is not contiguous".format(label))

    return {
        "status": "passed",
        "record_count": len(representations),
        "vector_master_count": sum(item["representation"] == "vector-master" for item in representations),
        "raster_source_count": sum(item["representation"] == "raster-source" for item in representations),
        "derived_export_count": sum(item["representation"] == "derived-export" for item in representations),
    }


def validate_output_index(index_bytes: bytes, files: dict[str, bytes]) -> dict[str, Any]:
    """Validate the packet's product-by-product proof and gap index."""
    index = _load_object(index_bytes, "output proof index")
    if index.get("schema_version") != 1:
        raise RepresentationError("Unsupported output proof index schema version")
    proof_path = _safe_path(index.get("proof_pdf_path"), "proof PDF path")
    proof = files.get(proof_path)
    if proof is None or not proof.startswith(b"%PDF-"):
        raise RepresentationError("Output proof index PDF is missing or unreadable")
    proof_digest = index.get("proof_sha256")
    if not isinstance(proof_digest, str) or hashlib.sha256(proof).hexdigest() != proof_digest:
        raise RepresentationError("Output proof index digest does not match the PDF")
    page_count = index.get("page_count")
    if not isinstance(page_count, int) or isinstance(page_count, bool) or page_count < 1:
        raise RepresentationError("Output proof index must declare a positive page count")
    outputs = index.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        raise RepresentationError("Output proof index must declare output coverage")
    seen_ids: set[str] = set()
    seen_pages: set[int] = set()
    for item in outputs:
        if not isinstance(item, dict):
            raise RepresentationError("Each output index row must be an object")
        output_id = item.get("output_id")
        status = item.get("status")
        if not isinstance(output_id, str) or not output_id or output_id in seen_ids:
            raise RepresentationError("Output index ids must be unique and non-empty")
        seen_ids.add(output_id)
        if status not in OUTPUT_STATUSES:
            raise RepresentationError("Output index has an unsupported status: {}".format(output_id))
        page = item.get("page")
        source_paths = item.get("source_paths", [])
        if status in ("current_proof", "historical_proof"):
            if not isinstance(page, int) or isinstance(page, bool) or not 1 <= page <= page_count:
                raise RepresentationError("Output index page is out of range: {}".format(output_id))
            if page in seen_pages:
                raise RepresentationError("Output index page is assigned to more than one output")
            seen_pages.add(page)
            if not isinstance(source_paths, list) or not source_paths:
                raise RepresentationError("Available proof rows must name their source files")
        elif page is not None:
            raise RepresentationError("Unavailable output rows must not claim a proof page")
        for source in source_paths:
            if _safe_path(source, "output index source path") not in files:
                raise RepresentationError("Output index source path is missing: {}".format(source))
    if seen_pages != set(range(1, page_count + 1)):
        raise RepresentationError("Output proof pages are not fully indexed")
    return {"status": "passed", "output_count": len(outputs), "proof_page_count": page_count}
