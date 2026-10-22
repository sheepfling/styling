#!/usr/bin/env python3
"""Audit a family long-form feature plan against exact shared-build PDF bytes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sheepfling_styling.document_components import ComponentProofError, audit_document_component_proof


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Optional JSON evidence destination")
    args = parser.parse_args()
    try:
        result = audit_document_component_proof(args.plan, args.report)
        payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            destination = args.output.resolve()
            if destination.exists():
                raise ComponentProofError("Output already exists; choose a fresh audit destination")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(payload, encoding="utf-8")
        print(payload, end="")
    except (ComponentProofError, OSError) as exc:
        print(f"Document component audit rejected: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
