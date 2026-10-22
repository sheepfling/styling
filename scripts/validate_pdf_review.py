#!/usr/bin/env python3
"""Validate a PDF screen-review receipt against its PDF and all page previews."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sheepfling_styling.pdf_review_receipt import ReviewError, validate_pdf_review_receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(validate_pdf_review_receipt(args.receipt), indent=2, sort_keys=True))
    except (ReviewError, OSError) as exc:
        print(f"PDF review rejected: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
