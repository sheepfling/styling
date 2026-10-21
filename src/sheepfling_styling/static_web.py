"""Validate and stage bounded, hash-pinned family-owned static web proofs.

This checks a deliberately small local HTML/CSS/SVG/PNG source contract. It
neither executes family code nor establishes browser layout or accessibility.
"""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
import posixpath
import re
import struct
from typing import Any
import xml.etree.ElementTree as ET

from .typography_roles import SHARED_TYPE_ROLES


class StaticWebError(ValueError):
    """The local static web declaration or its exact source is inconsistent."""


MEDIA_TYPES = {".html": "text/html", ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png",
               ".pdf": "application/pdf"}
FONT_SIGNATURES = (b"OTTO", b"ttcf", b"wOFF", b"wOF2", b"\x00\x01\x00\x00")
VOID_TAGS = {"area", "br", "col", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
FORBIDDEN_TAGS = {"script", "style", "iframe", "object", "embed", "base", "form", "audio", "video", "source",
                  "animate", "animatemotion", "animatetransform", "set", "foreignobject"}
URL_ATTRIBUTES = {"href", "src", "poster", "action", "formaction", "background", "xlink:href"}


def _path(value: Any) -> str:
    if (not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_./-]+", value)
            or value.startswith("/") or any(part in {"", ".", ".."} for part in value.split("/"))):
        raise StaticWebError("Web source paths must be safe, non-traversing relative paths")
    return value


def _local_reference(value: str, owner: str, files: dict[str, bytes], ids: set[str] | None = None) -> str | None:
    """Resolve this contract's explicit relative paths and local fragments only."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise StaticWebError(f"Empty or padded web reference in {owner}")
    path, separator, fragment = value.partition("#")
    if not path:
        if not separator or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]*", fragment):
            raise StaticWebError(f"Unsupported local fragment in {owner}: {value}")
        if ids is not None and fragment not in ids:
            raise StaticWebError(f"Missing fragment target in {owner}: {value}")
        return None
    _path(path)  # No URL schemes, query strings, escapes, data URLs or parent traversal.
    target = posixpath.join(posixpath.dirname(owner), path)
    if target not in files:
        raise StaticWebError(f"Undeclared local web reference in {owner}: {value}")
    if separator and fragment and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]*", fragment):
        raise StaticWebError(f"Unsupported local fragment in {owner}: {value}")
    if target == owner and separator and ids is not None and fragment not in ids:
        raise StaticWebError(f"Missing fragment target in {owner}: {value}")
    return target


def _css_checks(css: str, owner: str, files: dict[str, bytes]) -> dict[str, Any]:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    # A closed source subset keeps escaped URLs/imports outside this adapter's
    # claims. This is source validation, not an arbitrary CSS security parser.
    if "\\" in css or re.search(r"@import\b|expression\s*\(|-moz-binding|(?:^|[;{])\s*behavior\s*:", css, re.I):
        raise StaticWebError(f"Unsupported escaped or executable CSS in {owner}")
    urls = []
    for match in re.finditer(r"url\(\s*(?:\"([^\"]*)\"|'([^']*)'|([^)]*?))\s*\)", css, re.I):
        value = next(group for group in match.groups() if group is not None).strip()
        urls.append(value)
        _local_reference(value, owner, files)
    if len(urls) != len(re.findall(r"url\s*\(", css, re.I)):
        raise StaticWebError(f"Unparsed CSS URL in {owner}")
    roles = [role for role in SHARED_TYPE_ROLES if re.search(
        r"\[\s*data-type\s*=\s*([\"'])" + re.escape(role) + r"\1\s*\]", css)]
    return {"roles": roles, "focus_visible_rule": bool(re.search(r":focus-visible[^{}]*\{[^{}]+\}", css)),
            "responsive_media_rule": bool(re.search(r"@media[^{}]*\(\s*(?:min|max)-width\s*:\s*[0-9.]+(?:px|em|rem)\s*\)", css)),
            "reduced_motion_rule": bool(re.search(r"@media[^{}]*\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)", css)),
            "local_url_count": len(urls)}


class _Document(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.counts: dict[str, int] = {}
        self.ids: set[str] = set()
        self.roles: set[str] = set()
        self.references: list[tuple[str, str]] = []
        self.stylesheets: list[str] = []
        self.text: list[str] = []
        self.title: list[str] = []
        self.h1: list[str] = []
        self.language = ""
        self.viewport = False
        self.charset = False

    def handle_starttag(self, tag: str, pairs: list[tuple[str, str | None]]) -> None:
        if tag in FORBIDDEN_TAGS:
            raise StaticWebError(f"Static web HTML does not support <{tag}>")
        attributes = dict(pairs)
        if len(attributes) != len(pairs):
            raise StaticWebError("HTML attributes must not be duplicated")
        if any(key.startswith("on") or key in {"style", "srcdoc", "srcset", "ping"} for key in attributes):
            raise StaticWebError("Inline code, inline styles and unparsed resource attributes are not supported")
        for key, value in pairs:
            if value is not None and any(ord(character) < 32 for character in value):
                raise StaticWebError("HTML attributes may not contain control characters")
            if key in URL_ATTRIBUTES:
                self.references.append((key, value or ""))
            elif value and "url(" in value.lower():
                references = re.findall(r"url\(([^)]+)\)", value, flags=re.I)
                if len(references) != len(re.findall(r"url\(", value, flags=re.I)):
                    raise StaticWebError("Unparsed URL in HTML or inline SVG attribute")
                self.references.extend((key, reference.strip("\"' ")) for reference in references)
        self.counts[tag] = self.counts.get(tag, 0) + 1
        if tag == "html":
            self.language = attributes.get("lang") or ""
        if tag == "meta":
            if "http-equiv" in attributes:
                raise StaticWebError("HTTP-equivalent meta directives are unsupported in static web source")
            if (attributes.get("charset") or "").lower() == "utf-8":
                self.charset = True
            if (attributes.get("name") or "").lower() == "viewport":
                content = (attributes.get("content") or "").lower().replace(" ", "")
                self.viewport = "width=device-width" in content and bool(re.search(r"(?:^|,)initial-scale=1(?:\.0)?(?:,|$)", content))
        if tag == "link":
            if (attributes.get("rel") or "").lower() != "stylesheet":
                raise StaticWebError("Static web link elements must be local CSS stylesheets")
            self.stylesheets.append(attributes.get("href") or "")
        if "id" in attributes:
            value = attributes["id"] or ""
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]*", value) or value in self.ids:
                raise StaticWebError("HTML ids must be non-empty, safe and unique")
            self.ids.add(value)
        if "data-type" in attributes:
            role = attributes["data-type"] or ""
            if role not in SHARED_TYPE_ROLES:
                raise StaticWebError(f"Unknown shared web typography role: {role}")
            self.roles.add(role)
        if tag == "img" and "alt" not in attributes:
            raise StaticWebError("Web images must explicitly declare alt text or an empty decorative alt")
        if tag not in VOID_TAGS:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID_TAGS or not self.stack or self.stack.pop() != tag:
            raise StaticWebError(f"Static web HTML must explicitly balance its elements: {tag}")

    def handle_data(self, value: str) -> None:
        if "body" in self.stack:
            self.text.append(value)
        if "title" in self.stack:
            self.title.append(value)
        if "h1" in self.stack:
            self.h1.append(value)


def validate_static_web(declaration: Any, manifest_dir: Path, palettes: dict[str, Any],
                        required_copy: dict[str, str], role_map: dict[str, str]) -> dict[str, Any]:
    """Validate a bounded declaration before staging; return exact bytes + checks."""
    fields = {"schema_version", "id", "context", "palette", "entry", "dependencies", "required_text", "viewports"}
    if not isinstance(declaration, dict) or set(declaration) != fields or declaration["schema_version"] != "0.1.0":
        raise StaticWebError("Web declaration must use schema_version 0.1.0 and its exact declared fields")
    if (not isinstance(declaration["id"], str)
            or not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", declaration["id"])):
        raise StaticWebError("Web id must be a safe kebab-case identifier")
    if (declaration["context"] not in ("light", "dark", "white", "mixed")
            or not isinstance(declaration["palette"], str) or declaration["palette"] not in palettes):
        raise StaticWebError("Web context and palette must be explicitly declared")
    refs = declaration["required_text"]
    if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) for ref in refs) or len(set(refs)) != len(refs):
        raise StaticWebError("Web required_text must be a non-empty unique list of content references")
    if set(refs) != set(required_copy):
        raise StaticWebError("Web required copy must resolve every declared content reference")
    dependencies = declaration["dependencies"]
    if not isinstance(dependencies, list) or not 1 <= len(dependencies) <= 64:
        raise StaticWebError("Web dependencies must contain 1 to 64 hash-pinned local files")
    records = [declaration["entry"], *dependencies]
    files: dict[str, bytes] = {}
    metadata: list[dict[str, Any]] = []
    base: PurePosixPath | None = None
    for index, record in enumerate(records):
        if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
            raise StaticWebError("Web source records must declare exactly path and sha256")
        name = _path(record["path"])
        path = manifest_dir / name
        suffix = path.suffix.lower()
        if index == 0:
            if suffix != ".html":
                raise StaticWebError("Web entry must be a UTF-8 .html document")
            base = PurePosixPath(name).parent
        elif suffix not in {".css", ".svg", ".png", ".pdf"}:
            raise StaticWebError("Web dependencies support only CSS, SVG, PNG and PDF; font binaries and executable code are omitted")
        assert base is not None
        if not PurePosixPath(name).is_relative_to(base):
            raise StaticWebError("Web dependencies must stay inside the entry directory")
        staged = PurePosixPath(name).relative_to(base).as_posix()
        if staged in files:
            raise StaticWebError("Web source destinations must be unique")
        for ancestor in (path, *path.parents):
            if ancestor == manifest_dir:
                break
            if ancestor.is_symlink():
                raise StaticWebError("Web sources must not pass through symlinks")
        if not path.resolve().is_relative_to(manifest_dir.resolve()) or not path.is_file():
            raise StaticWebError(f"Missing or escaping web source: {name}")
        limit = 8_388_608 if suffix in {".png", ".pdf"} else 1_048_576
        if path.stat().st_size > limit:
            raise StaticWebError(f"Web source exceeds its bounded file limit: {name}")
        raw = path.read_bytes()
        if (not isinstance(record["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"])
                or hashlib.sha256(raw).hexdigest() != record["sha256"]):
            raise StaticWebError(f"Web source hash differs: {name}")
        if raw.startswith(FONT_SIGNATURES):
            raise StaticWebError("Font binaries must not be disguised as static web sources")
        files[staged] = raw
        metadata.append({"path": staged, "source_path": name, "sha256": record["sha256"], "bytes": len(raw),
                         "media_type": MEDIA_TYPES[suffix], "representation": "family-owned-static-source",
                         "editable": suffix in {".html", ".css", ".svg"}})
    if sum(map(len, files.values())) > 16_777_216:
        raise StaticWebError("Static web sources exceed 16 MiB total")
    viewports = declaration["viewports"]
    if not isinstance(viewports, list) or not 3 <= len(viewports) <= 8:
        raise StaticWebError("Web viewports must declare 3 to 8 intended browser test dimensions")
    widths = []
    for viewport in viewports:
        if (not isinstance(viewport, dict) or set(viewport) != {"width", "height"}
                or type(viewport["width"]) is not int or not 320 <= viewport["width"] <= 2560
                or type(viewport["height"]) is not int or not 480 <= viewport["height"] <= 2160):
            raise StaticWebError("Web viewports need integer width 320–2560 and height 480–2160 CSS pixels")
        widths.append(viewport["width"])
    if len(set(widths)) != len(widths) or min(widths) > 480 or max(widths) < 1200:
        raise StaticWebError("Web viewports must include distinct mobile, intermediate and desktop widths")
    entry = metadata[0]["path"]
    document = _Document()
    css_checks = {}
    css_sources = {}
    for record in metadata:
        name, raw = record["path"], files[record["path"]]
        if record["media_type"] == "application/pdf":
            if not raw.startswith(b"%PDF-"):
                raise StaticWebError(f"Linked web PDF must contain PDF bytes: {name}")
            record["representation"] = "linked-pdf-document"
            continue
        if record["media_type"] == "image/png":
            if len(raw) < 33 or not raw.startswith(b"\x89PNG\r\n\x1a\n") or raw[12:16] != b"IHDR":
                raise StaticWebError(f"Web PNG has no readable geometry: {name}")
            width, height = struct.unpack(">II", raw[16:24])
            if not 1 <= width <= 8192 or not 1 <= height <= 8192:
                raise StaticWebError(f"Web PNG dimensions exceed 8192 pixels: {name}")
            record.update({"width": width, "height": height})
            continue
        try:
            source = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise StaticWebError(f"Static web text source must be UTF-8: {name}") from exc
        if record["media_type"] == "text/html":
            document.feed(source)
            document.close()
        elif record["media_type"] == "text/css":
            css_checks[name] = _css_checks(source, name, files)
            css_sources[name] = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
        else:
            try:
                if ("<!DOCTYPE" in source.upper() or "<!ENTITY" in source.upper()
                        or "<?xml-stylesheet" in source.lower()):
                    raise StaticWebError("SVG entity declarations are unsupported")
                tree = ET.fromstring(source)
            except ET.ParseError as exc:
                raise StaticWebError(f"Malformed static web SVG: {name}") from exc
            if tree.tag.split("}")[-1] != "svg":
                raise StaticWebError(f"Web SVG must have an svg root: {name}")
            for element in tree.iter():
                if element.tag.split("}")[-1].lower() in FORBIDDEN_TAGS | {"foreignobject"}:
                    raise StaticWebError(f"Active or embedded SVG content is unsupported: {name}")
                for attribute, value in element.attrib.items():
                    attribute = attribute.split("}")[-1].lower()
                    if attribute.startswith("on") or attribute == "style":
                        raise StaticWebError(f"Inline executable SVG or CSS is unsupported: {name}")
                    if attribute in {"href", "src"}:
                        _local_reference(value, name, files)
                    for match in re.finditer(r"url\(([^)]+)\)", value, re.I):
                        _local_reference(match[1].strip("\"' "), name, files)
    if document.stack or not re.fullmatch(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*", document.language):
        raise StaticWebError("Web HTML needs balanced elements and an explicit language")
    for tag in ("html", "head", "body", "main", "h1", "title"):
        if document.counts.get(tag) != 1:
            raise StaticWebError(f"Web HTML must contain exactly one {tag}")
    if any(not document.counts.get(tag) for tag in ("header", "nav", "footer")):
        raise StaticWebError("Web HTML must declare header, nav and footer landmarks")
    if not document.viewport or not document.charset or not "".join(document.title).strip() or not "".join(document.h1).strip():
        raise StaticWebError("Web HTML needs UTF-8, a device viewport, a title and a non-empty h1")
    for _, reference in document.references:
        _local_reference(reference, entry, files, document.ids)
    if not document.stylesheets or any(not value.endswith(".css") for value in document.stylesheets):
        raise StaticWebError("Web HTML needs at least one declared local CSS stylesheet")
    linked_css = [css_checks[_local_reference(value, entry, files)] for value in document.stylesheets]
    linked_source = "\n".join(css_sources[_local_reference(value, entry, files)] for value in document.stylesheets)
    normalized = " ".join(" ".join(document.text).split())
    for reference, text in required_copy.items():
        if " ".join(text.split()) not in normalized:
            raise StaticWebError(f"Web body is missing required copy: {reference}")
    roles = {role for check in linked_css for role in check["roles"]}
    if roles != set(SHARED_TYPE_ROLES):
        raise StaticWebError("Web CSS must declare selectors for all 17 shared semantic type roles")
    if set(role_map) != set(SHARED_TYPE_ROLES):
        raise StaticWebError("Web role bindings must map all 17 shared semantic type roles")
    for role, face in role_map.items():
        if not isinstance(face, str) or not re.fullmatch(r"[a-z]+", face):
            raise StaticWebError("Web physical face ids must be safe identifiers")
        selector = r"\[\s*data-type\s*=\s*([\"'])" + re.escape(role) + r"\1\s*\]"
        blocks = re.findall(selector + r"[^{}]*\{([^{}]*)\}", linked_source)
        if not any(re.search(r"(?:^|;)\s*font-family\s*:\s*var\(\s*--face-" + re.escape(face) + r"\s*\)\s*(?:;|$)", block[1])
                   for block in blocks):
            raise StaticWebError(f"Web semantic selector must apply role_map via --face-{face}: {role}")
        if not re.search(r"--face-" + re.escape(face) + r"\s*:\s*[^;{}]+[;}]", linked_source):
            raise StaticWebError(f"Web CSS must declare the family-owned --face-{face} font stack")
    for key in ("focus_visible_rule", "responsive_media_rule", "reduced_motion_rule"):
        if not any(check[key] for check in linked_css):
            raise StaticWebError(f"Web CSS must include a {key}")
    return {"entry": entry, "files": files, "sources": metadata,
            "checks": {"status": "static-checks-passed-awaiting-browser-review", "language": document.language,
                       "landmarks": {tag: document.counts[tag] for tag in ("header", "nav", "main", "footer")},
                       "heading_count": 1, "viewport_meta": True, "required_text": list(required_copy),
                       "shared_type_role_selectors": len(roles), "exercised_type_roles": sorted(document.roles),
                       "semantic_role_bindings": role_map,
                       "local_references_only": True, "font_binaries_copied": False,
                       "focus_visible_rule": True, "responsive_media_rule": True, "reduced_motion_rule": True,
                       "intended_viewports": viewports, "browser_review": "pending",
                       "limits": ["Static signals do not establish computed layout, contrast, keyboard order or accessibility.",
                                  "Declared viewport dimensions are intended checks; no browser has run in this adapter.",
                                  "CSS font stacks remain family-owned; PDF font hashes do not prove browser font selection."]}}
