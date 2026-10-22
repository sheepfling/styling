#!/usr/bin/env python3
"""Check a supported local build mode before running a family export."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

MODES = {
    "recipe": ("xelatex", "pdfinfo", "pdftotext", "pdffonts", "pdftoppm"),
    "legacy": ("tectonic", "pdfinfo", "pdftotext", "pdffonts", "rsvg-convert"),
    "starter": ("rsvg-convert",),
    "native-tex": ("xelatex", "pdftotext", "pdffonts", "pdftoppm"),
    "native-vector": ("rsvg-convert",),
}
VERSION_ARGS = {"xelatex": "--version", "tectonic": "--version", "rsvg-convert": "--version"}


def _tool(name: str) -> dict[str, str | None]:
    executable = shutil.which(name)
    if executable is None:
        return {"status": "missing", "path": None, "version": None}
    command = [executable, VERSION_ARGS.get(name, "-v")]
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=10, check=False)
        first_line = (result.stdout + "\n" + result.stderr).strip().splitlines()[0]
    except (OSError, subprocess.TimeoutExpired, IndexError):
        first_line = None
    return {"status": "present", "path": executable, "version": first_line}


def _package(name: str) -> dict[str, str | None]:
    try:
        return {"status": "present", "version": importlib.metadata.version(name)}
    except importlib.metadata.PackageNotFoundError:
        return {"status": "missing", "version": None}


def diagnose(mode: str, style_path: Path | None = None) -> dict[str, object]:
    if mode not in MODES:
        raise ValueError("Unsupported build mode")
    if style_path is not None and mode != "recipe":
        raise ValueError("--style font preflight currently supports recipe mode")
    tools = {name: _tool(name) for name in MODES[mode]}
    packages = {name: _package(name) for name in ("pypdf", "Pillow")}
    python_ok = sys.version_info >= (3, 11)
    fonts: dict[str, dict[str, str]] = {}
    if style_path is not None:
        sys.path.insert(0, str(ROOT / "scripts"))
        from build_recipe_suite import font_source, read_object
        style = read_object(style_path)
        if "recipe_version" not in style or not isinstance(style.get("type"), dict):
            raise ValueError("--style needs a composition recipe with declared type faces")
        for role, face in style["type"].items():
            try:
                font_source(style_path.parent, face, role)
                fonts[role] = {"status": "hash-matched", "sha256": face["sha256"]}
            except (OSError, ValueError) as exc:
                fonts[role] = {"status": "unavailable", "reason": str(exc)}
    missing = ([f"tool:{name}" for name, data in tools.items() if data["status"] != "present"]
               + [f"package:{name}" for name, data in packages.items() if data["status"] != "present"]
               + [f"font:{name}" for name, data in fonts.items() if data["status"] != "hash-matched"])
    if not python_ok:
        missing.append("python>=3.11")
    return {"mode": mode, "status": "ready" if not missing else "missing-dependencies",
            "python": {"version": sys.version.split()[0], "supported": python_ok},
            "tools": tools, "packages": packages, "fonts": fonts, "missing": missing}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=sorted(MODES), default="recipe")
    parser.add_argument("--style", type=Path, help="Optional composition recipe for exact font-hash preflight")
    args = parser.parse_args()
    try:
        report = diagnose(args.mode, args.style)
    except (OSError, ValueError) as exc:
        print(f"Build doctor rejected: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
