#!/usr/bin/env python3
"""Validate one profile-owned source and readiness intake record."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sheepfling_styling.customer_intake import IntakeError, load_and_validate_intake


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("intake", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(load_and_validate_intake(args.intake), indent=2, sort_keys=True))
    except (IntakeError, OSError) as exc:
        print(f"Customer intake rejected: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
