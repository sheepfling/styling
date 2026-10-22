#!/usr/bin/env python3
"""Print a customer-neutral coverage report for the six profile slots."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sheepfling_styling.portfolio_coverage import CoverageError, build_portfolio_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, help="Private directory with optional system-XX.json coverage files")
    parser.add_argument("--intake-dir", type=Path, help="Private directory with optional system-XX.json intake files")
    parser.add_argument("--output", type=Path, help="Write the report here instead of stdout")
    args = parser.parse_args()
    try:
        report = build_portfolio_report(ROOT, args.evidence_dir, args.intake_dir)
        rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
    except (CoverageError, OSError, ValueError) as exc:
        print(f"Portfolio report rejected: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
