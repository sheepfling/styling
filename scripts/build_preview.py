"""Build one synthetic SVG/PDF proof through the shared asset contracts."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pypdf import PdfReader

from sheepfling_styling.asset_pack_contract import load_asset_pack
from sheepfling_styling.pdf_output_intent import add_srgb_output_intent
from sheepfling_styling.visual_representations import (
    validate_output_index, validate_representation_contract, validate_visual_representations,
)

PROFILE = "examples/starter/profile.json"

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def safe_color(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
        raise ValueError("Example color tokens must be six-digit hex colors")
    return value

def build(root: Path, output_dir: Path) -> dict[str, object]:
    root = root.resolve()
    output_dir = output_dir.resolve()
    if not output_dir.is_relative_to(root):
        raise ValueError("Output directory must stay inside the repository root")
    profile = json.loads((root / PROFILE).read_text(encoding="utf-8"))
    tokens = json.loads((root / profile["tokens_path"]).read_text(encoding="utf-8"))
    pack = load_asset_pack(root, "contracts/asset-packs.json", profile["asset_pack_id"])
    if len(pack["assets"]) != 1 or not pack["assets"][0]["resolved_local"]:
        raise ValueError("Starter build requires its exact single local vector asset")
    mark = pack["assets"][0]
    mark_root = ET.fromstring((root / mark["path"]).read_bytes())
    mark_viewbox = mark_root.attrib.get("viewBox", "0 0 120 120")
    mark_content = "".join(ET.tostring(child, encoding="unicode") for child in list(mark_root))
    output_dir.mkdir(parents=True, exist_ok=True)
    svg_path = output_dir / "preview.svg"
    pdf_path = output_dir / "preview.pdf"
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="816" height="1056" viewBox="0 0 816 1056">
<rect width="816" height="1056" fill="{safe_color(tokens['paper'])}"/>
<rect x="64" y="64" width="688" height="928" rx="28" fill="#FFFFFF" stroke="#D5DCD6" stroke-width="2"/>
<path d="M96 108h624" stroke="{safe_color(tokens['accent'])}" stroke-width="8" stroke-linecap="round"/>
<text x="96" y="188" font-family="sans-serif" font-size="18" letter-spacing="3" fill="{safe_color(tokens['accent'])}">SYNTHETIC PROFILE SPECIMEN</text>
<text x="96" y="270" font-family="sans-serif" font-size="52" font-weight="700" fill="{safe_color(tokens['ink'])}">Shared styling base</text>
<text x="96" y="316" font-family="sans-serif" font-size="23" fill="{safe_color(tokens['ink'])}">One isolated profile, one bounded proof.</text>
<svg x="96" y="386" width="120" height="120" viewBox="{mark_viewbox}">{mark_content}</svg>
<rect x="96" y="566" width="624" height="122" rx="16" fill="{safe_color(tokens['accent'])}"/>
<text x="128" y="618" font-family="sans-serif" font-size="16" letter-spacing="2" fill="#FFFFFF">ASSET PACK</text>
<text x="128" y="660" font-family="sans-serif" font-size="24" font-weight="700" fill="#FFFFFF">Hash-pinned vector source</text>
<rect x="96" y="724" width="624" height="92" rx="16" fill="{safe_color(tokens['highlight'])}"/>
<text x="128" y="781" font-family="sans-serif" font-size="22" fill="{safe_color(tokens['ink'])}">Output status: current proof</text>
<text x="96" y="920" font-family="sans-serif" font-size="14" fill="#55635F">Generated from a synthetic fixture for contract and export verification.</text>
</svg>
'''
    svg_path.write_text(svg, encoding="utf-8")
    subprocess.run(["rsvg-convert", "--format=pdf", "--output", str(pdf_path), str(svg_path)], check=True)
    add_srgb_output_intent(pdf_path)
    page_count = len(PdfReader(str(pdf_path)).pages)
    rel_svg = svg_path.relative_to(root).as_posix()
    rel_pdf = pdf_path.relative_to(root).as_posix()
    source_paths = [PROFILE, profile["tokens_path"], mark["path"], rel_svg]
    representation = {
        "interface_id": "visual-asset-representations", "interface_version": "0.1.0", "schema_version": 1,
        "representations": [
            {"id": "starter-mark", "representation": "vector-master", "path": mark["path"], "sha256": mark["sha256"], "linked_raster_sources": [], "editable": True},
            {"id": "starter-proof", "representation": "derived-export", "path": rel_pdf, "sha256": sha256(pdf_path.read_bytes()),
             "source_paths": source_paths, "generator": "scripts/build_preview.py + rsvg-convert",
             "rendering": "single-page vector PDF with sRGB output intent", "format": "PDF", "page_count": page_count,
             "page_map": [{"page": 1, "source_paths": source_paths}]},
        ],
    }
    files = {p: (root / p).read_bytes() for p in source_paths}
    files[rel_pdf] = pdf_path.read_bytes()
    contract = (root / "contracts/visual-asset-representations.json").read_bytes()
    validate_representation_contract(contract)
    representation_bytes = (json.dumps(representation, indent=2) + "\n").encode("utf-8")
    checks = validate_visual_representations(representation_bytes, files)
    index = {"schema_version": 1, "proof_pdf_path": rel_pdf, "proof_sha256": sha256(files[rel_pdf]),
             "page_count": page_count, "outputs": [{"output_id": "starter-preview", "status": "current_proof",
             "page": 1, "source_paths": source_paths}]}
    index_bytes = (json.dumps(index, indent=2) + "\n").encode("utf-8")
    validate_output_index(index_bytes, files)
    (output_dir / "representations.json").write_bytes(representation_bytes)
    (output_dir / "output-index.json").write_bytes(index_bytes)
    return {"status": "passed", "page_count": page_count, "pdf": rel_pdf, "pdf_sha256": sha256(files[rel_pdf]),
            "representation_validation": checks, "srgb_output_intent": True}

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "examples/starter/output")
    args = parser.parse_args()
    result = build(args.root, args.output_dir)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
