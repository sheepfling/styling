"""Prove trusted, family-owned TeX packets through shared output checks."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

from pypdf import PdfReader

from .customer_intake import IntakeError, pinned_file, read_intake
from .family_coverage import coverage_from_outputs
from .visual_representations import validate_visual_representations

ID = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
SOURCE_EXTENSIONS = {".tex", ".sty", ".ttf", ".otf", ".woff", ".woff2", ".png", ".jpg", ".jpeg", ".svg", ".pdf", ".icc", ".json", ".txt", ".html", ".css"}
SLOTS = {"document-one-page": {1}, "document-two-page": {2}, "product-slick": {1, 2}, "component-proof": {6}}


class NativeTexError(ValueError):
    """A trusted native TeX packet is incomplete, stale, or did not compile as declared."""


def _read(path: Path) -> dict[str, Any]:
    try:
        return read_intake(path)
    except IntakeError as exc:
        raise NativeTexError(str(exc)) from exc


def _pin(root: Path, record: Any, label: str) -> Path:
    try:
        path = pinned_file(root, record, label)
    except IntakeError as exc:
        raise NativeTexError(str(exc)) from exc
    if path.suffix.lower() not in SOURCE_EXTENSIONS:
        raise NativeTexError(f"{label} has an unsupported source format")
    return path


def validate_manifest(manifest_path: Path) -> dict[str, Any]:
    data = _read(manifest_path)
    required = {"schema_version", "family_id", "source_state", "route", "sources", "outputs", "srgb_icc"}
    if not required.issubset(data) or set(data) - required - {"web_source"} or data["schema_version"] != "0.1.0":
        raise NativeTexError("Unsupported native TeX manifest")
    if not isinstance(data["family_id"], str) or not ID.fullmatch(data["family_id"]):
        raise NativeTexError("family_id must be a safe identifier")
    if not isinstance(data["source_state"], str) or data["source_state"] not in {"selected-for-now", "proposed-unselected"}:
        raise NativeTexError("Unsupported native TeX source state")
    if not isinstance(data["route"], str) or not ID.fullmatch(data["route"]):
        raise NativeTexError("Native TeX route must be a safe identifier")
    root = manifest_path.parent.resolve()
    sources = data["sources"]
    if not isinstance(sources, list) or not sources or len(sources) > 128:
        raise NativeTexError("Native TeX packet needs one to 128 pinned sources")
    names: set[str] = set()
    for index, record in enumerate(sources):
        path = _pin(root, record, f"sources[{index}]")
        name = path.relative_to(root).as_posix()
        if name in names or path.stat().st_size > 20 * 1024 * 1024:
            raise NativeTexError("Native TeX sources must be unique and bounded")
        names.add(name)
    icc = _pin(root, data["srgb_icc"], "srgb_icc")
    if icc.suffix.lower() != ".icc" or icc.relative_to(root).as_posix() not in names:
        raise NativeTexError("sRGB ICC must be a declared source")
    if "web_source" in data:
        web = data["web_source"]
        if not isinstance(web, dict) or set(web) != {"entry", "dependencies"} or not isinstance(web["dependencies"], list):
            raise NativeTexError("web_source needs an entry and dependency list")
        web_paths = []
        for label, record in [("web_source.entry", web["entry"]), *[(f"web_source.dependencies[{i}]", item) for i, item in enumerate(web["dependencies"])]]:
            path = _pin(root, record, label)
            name = path.relative_to(root).as_posix()
            if name not in names or name in web_paths:
                raise NativeTexError("web_source files must be distinct declared sources")
            web_paths.append(name)
        if not web_paths or not web_paths[0].endswith(".html") or len(web_paths) < 2:
            raise NativeTexError("web_source needs HTML and its declared dependencies")
    outputs = data["outputs"]
    if not isinstance(outputs, list) or not outputs or len(outputs) > 16:
        raise NativeTexError("Native TeX packet needs one to sixteen outputs")
    ids: set[str] = set()
    for index, output in enumerate(outputs):
        if not isinstance(output, dict) or set(output) != {"id", "slot", "context", "entry", "page_count", "page_pt", "required_text", "passes"}:
            raise NativeTexError(f"outputs[{index}] has missing or extra fields")
        output_id = output["id"]
        if not isinstance(output_id, str) or not ID.fullmatch(output_id) or output_id in ids:
            raise NativeTexError("Native TeX output IDs must be distinct safe identifiers")
        ids.add(output_id)
        if (output["slot"] is not None and (not isinstance(output["slot"], str) or output["slot"] not in SLOTS)) or output["context"] != "light":
            raise NativeTexError("Native TeX outputs support light PDF baseline slots or experimental null")
        if data["source_state"] == "proposed-unselected" and output["slot"] is not None:
            raise NativeTexError("Unselected TeX outputs cannot claim baseline coverage")
        if type(output["page_count"]) is not int or not 1 <= output["page_count"] <= 32:
            raise NativeTexError("Native TeX page_count must be 1 to 32")
        if output["slot"] is not None and output["page_count"] not in SLOTS[output["slot"]]:
            raise NativeTexError("Native TeX page count does not satisfy its slot")
        page = output["page_pt"]
        if not isinstance(page, list) or len(page) != 2 or any(type(n) not in (int, float) or not 100 <= n <= 1500 for n in page):
            raise NativeTexError("Native TeX page_pt must be two point dimensions")
        entry = _pin(root, output["entry"], f"{output_id}.entry")
        if entry.suffix.lower() != ".tex" or entry.relative_to(root).as_posix() not in names:
            raise NativeTexError("Native TeX entry must be a declared .tex source")
        if type(output["passes"]) is not int or output["passes"] not in {1, 2, 3}:
            raise NativeTexError("Native TeX passes must be 1 to 3")
        if not isinstance(output["required_text"], list) or not output["required_text"] or any(not isinstance(text, str) or not text.strip() for text in output["required_text"]):
            raise NativeTexError("Native TeX required_text must contain non-empty strings")
    return {"manifest": data, "root": root}


def _run(command: list[str], cwd: Path) -> str:
    try:
        return subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise NativeTexError(f"Native TeX command failed: {getattr(exc, 'stdout', '')[-1500:]} {getattr(exc, 'stderr', '')[-1500:]}") from exc


def build(manifest_path: Path, output_dir: Path) -> dict[str, Any]:
    plan = validate_manifest(manifest_path)
    xelatex = shutil.which("xelatex")
    pdftotext = shutil.which("pdftotext")
    pdffonts = shutil.which("pdffonts")
    pdftoppm = shutil.which("pdftoppm")
    if not all((xelatex, pdftotext, pdffonts, pdftoppm)):
        raise NativeTexError("XeLaTeX and Poppler tools are required for native TeX proofs")
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise NativeTexError("Choose a new output directory for the native TeX proof")
    source_root = output_dir / "source"
    source_root.mkdir(parents=True)
    manifest = plan["manifest"]
    web_names = ({manifest["web_source"]["entry"]["path"],
                  *[item["path"] for item in manifest["web_source"]["dependencies"]]} if "web_source" in manifest else set())
    manifest_raw = manifest_path.read_bytes()
    (output_dir / "input-manifest.json").write_bytes(manifest_raw)
    for record in manifest["sources"]:
        name = record["path"]
        target = source_root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(plan["root"] / name, target)
    files = {"source/" + record["path"]: (source_root / record["path"]).read_bytes() for record in manifest["sources"]}
    representations = []
    icc_raw = (source_root / manifest["srgb_icc"]["path"]).read_bytes()
    report_outputs = []
    for output in manifest["outputs"]:
        output_id = output["id"]
        compiled = output_dir / "compiled" / output_id
        compiled.mkdir(parents=True)
        entry = source_root / output["entry"]["path"]
        command = [xelatex, "-no-shell-escape", "-halt-on-error", "-interaction=nonstopmode",
                   "-output-directory=" + str(compiled), "-jobname=" + output_id, str(entry)]
        for _ in range(output["passes"]):
            _run(command, source_root)
        pdf = compiled / f"{output_id}.pdf"
        if not pdf.is_file():
            raise NativeTexError(f"{output_id} did not create a PDF")
        log = (compiled / f"{output_id}.log").read_text(encoding="utf-8", errors="replace")
        if re.search(r"Overfull \\[hv]box|Missing character|Undefined control sequence|LaTeX Error|Citation .* undefined", log, re.I):
            raise NativeTexError(f"{output_id} has TeX or layout diagnostics")
        reader = PdfReader(str(pdf))
        if len(reader.pages) != output["page_count"]:
            raise NativeTexError(f"{output_id} page count differs from its declaration")
        for page in reader.pages:
            if any(abs(float(actual) - declared) > .5 for actual, declared in zip((page.mediabox.width, page.mediabox.height), output["page_pt"])):
                raise NativeTexError(f"{output_id} page geometry differs from its declaration")
        root = reader.trailer["/Root"]
        intents = root.get("/OutputIntents", [])
        if not intents or intents[0].get_object().get("/DestOutputProfile") is None:
            raise NativeTexError(f"{output_id} lacks an sRGB OutputIntent")
        profile = intents[0].get_object()["/DestOutputProfile"].get_object().get_data()
        if hashlib.sha256(profile).digest() != hashlib.sha256(icc_raw).digest():
            raise NativeTexError(f"{output_id} OutputIntent differs from declared ICC bytes")
        text = " ".join(_run([pdftotext, str(pdf), "-"], source_root).split())
        if any(" ".join(needle.split()) not in text for needle in output["required_text"]):
            raise NativeTexError(f"{output_id} is missing required extracted text")
        fonts = _run([pdffonts, str(pdf)], source_root).splitlines()[2:]
        if not fonts or any(not all(field == "yes" for field in line.split()[-5:-2]) for line in fonts if line.strip()):
            raise NativeTexError(f"{output_id} has missing or unembedded fonts")
        pdf_target = output_dir / "pdf" / f"{output_id}.pdf"
        pdf_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pdf, pdf_target)
        preview_prefix = output_dir / "previews" / output_id
        preview_prefix.parent.mkdir(parents=True, exist_ok=True)
        _run([pdftoppm, "-r", "120", "-png", str(pdf_target), str(preview_prefix)], source_root)
        previews = sorted(preview_prefix.parent.glob(f"{output_id}-*.png"))
        if len(previews) != output["page_count"]:
            raise NativeTexError(f"{output_id} preview count differs from PDF pages")
        pdf_raw = pdf_target.read_bytes()
        pdf_name = pdf_target.relative_to(output_dir).as_posix()
        files[pdf_name] = pdf_raw
        source_paths = ["source/" + output["entry"]["path"],
                        *["source/" + record["path"] for record in manifest["sources"]
                          if record["path"] not in web_names and Path(record["path"]).suffix.lower() in {".ttf", ".otf", ".png", ".pdf", ".icc"}]]
        representations.append({"id": f"pdf-{output_id}", "representation": "derived-export",
                                "path": pdf_name, "sha256": hashlib.sha256(pdf_raw).hexdigest(),
                                "source_paths": source_paths, "generator": "native-tex + XeLaTeX",
                                "rendering": "family-owned TeX to sRGB screen PDF", "format": "PDF", "page_count": len(reader.pages),
                                "page_map": [{"page": index, "source_paths": source_paths} for index in range(1, len(reader.pages) + 1)]})
        report_outputs.append({"id": output_id, "slot": output["slot"], "context": output["context"],
                               "status": "built-awaiting-visual-review", "page_count": len(reader.pages),
                               "page_pt": output["page_pt"], "pdf": {"path": pdf_target.relative_to(output_dir).as_posix(),
                               "sha256": hashlib.sha256(pdf_raw).hexdigest()},
                               "previews": [{"path": path.relative_to(output_dir).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in previews],
                               "entry_sha256": output["entry"]["sha256"], "sRGB_output_intent": True,
                               "embedded_fonts": True})
    metadata = {"interface_id": "visual-asset-representations", "interface_version": "0.1.0",
                "schema_version": 1, "representations": representations}
    representation_check = validate_visual_representations(json.dumps(metadata).encode(), files)
    (output_dir / "representations.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    coverage = coverage_from_outputs(report_outputs)
    web_report = None
    if "web_source" in manifest:
        web = manifest["web_source"]
        web_report = {"status": "source-only", "entry": web["entry"], "dependencies": web["dependencies"],
                      "static_review": "pending", "browser_review": "pending"}
        coverage["web-light"] = {"status": "source-only", "outputs": []}
    report = {"schema_version": "0.1.0", "family_id": manifest["family_id"], "route": manifest["route"],
              "source_state": manifest["source_state"], "outputs": report_outputs,
              "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
              "coverage": coverage, "web_source": web_report,
              "representation_check": representation_check,
              "sources": manifest["sources"], "review": "pending", "publication": "not-cleared-by-this-build",
              "semantic_role_binding": "family-owned native TeX; declared mapping must be reviewed separately"}
    (output_dir / "build-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
