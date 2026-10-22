#!/usr/bin/env python3
"""Audit pinned family proofs without changing their composition or approval state."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sheepfling_styling.family_system import FamilySystemError, audit_family_system


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, help="Write the audit JSON to this private path")
    args = parser.parse_args()
    try:
        report = audit_family_system(args.manifest)
    except FamilySystemError as exc:
        parser.exit(2, f"family system audit: {exc}\n")
    raw = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(raw, encoding="utf-8")
    else:
        print(raw, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
