# Shared styling foundation

A small, source-aware foundation for independent visual systems. It defines reusable profile and asset-pack contracts, validates asset provenance and output proofs, and demonstrates one bounded SVG-to-PDF build. The shared typography deliverable contract defines a common light-context baseline of one-page and two-page documents, responsive web, product slicks, and component proofs for six neutral profile slots; family-specific type, identity, accents, and compositions stay in their own recipes.

See [the typography output suite](docs/typography-output-suite.md) for the common light-context slots, family-owned type roles, and local build checks.

The registry reserves six neutral profile slots without identity artwork, fonts, or active brand values. Each slot starts source-review-pending until its exact sources, rights, and approved direction are recorded.

## Quick start

Use Python 3.11 or newer. The validation package has no third-party dependencies. The one-page example uses librsvg (`rsvg-convert`), Pillow and pypdf. Install the optional Python preview dependencies with `python -m pip install -e ".[preview]"`.

```sh
python -m unittest discover -s tests -v
python scripts/build_preview.py
```

The example writes an editable SVG, a vector PDF with an sRGB output intent, and hash-pinned representation/output-index records under `examples/starter/output/`.

See [the boundary and promotion rules](docs/architecture.md) before adding a source profile.

The profile-agnostic family exporter in `scripts/build_family_typesetting_suite.py` applies the same five light-context outputs to an explicit style manifest and content fixture: one-page document, two-page document, responsive web-light page, product slick, and six-page component proof. See [the typography suite notes](docs/typography-output-suite.md) for the role, accent, and verification rules.
