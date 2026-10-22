# Local build environment

Run `python scripts/doctor.py --mode recipe` before a composition-recipe export. The diagnostic reports the selected Python interpreter, XeLaTeX, Poppler tools, `pypdf`, and Pillow. `--style /path/to/recipe.json` also checks every declared font file against its exact hash without copying the font into the public source package. Use `--mode legacy` for the older Tectonic adapter and `--mode starter` for the synthetic SVG preview.

The documented local reference environment on 2026-10-21 is macOS with Python 3.12.3, XeTeX from TeX Live 2023, Poppler 26.10.0, pypdf 6.1.0, and Pillow 11.2.1. Recipe builds require Python 3.11 or newer, the commands listed by the diagnostic, and the optional Python packages in `pyproject.toml`. The legacy mode additionally requires Tectonic; it is absent in the current local environment. The builder records exact tool versions in its output report.

The native TeX adapter uses XeLaTeX and Poppler plus `pypdf`; preflight with `python scripts/doctor.py --mode native-tex`. The native SVG adapter uses librsvg's `rsvg-convert`, Pillow and `pypdf`; preflight with `--mode native-vector`. Its JPEG support is checked from exact source bytes. Both operate on private, trusted family packets and create private proof outputs. The legacy Tectonic-dependent family-template builder is a separate path and does not replace a native family composition.

This is a known local baseline, not a hermetic release image or a cross-platform support claim. Pinning a repeatable CI environment and publishing a release matrix remain open in MAT-007/MAT-008. Family fonts stay external and hash checked; their licenses and redistribution limits belong in the customer intake.

A reviewed hosted CI workflow and its first successful result are still needed before Ubuntu is counted as a supported release environment.
