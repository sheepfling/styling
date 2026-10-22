# Shared styling foundation

A small, source-aware foundation for independent visual systems. It defines reusable profile and asset-pack contracts, validates asset provenance and output proofs, and demonstrates one bounded SVG-to-PDF build. The shared typography deliverable contract defines a common light-context baseline of one-page and two-page documents, responsive web, and product slicks for all six separate profiles; family-specific type, identity, and accents stay in their own recipes.

See [the typography output suite](docs/typography-output-suite.md) for the common light-context slots, family-owned type roles, and local build checks.

The registry reserves six separate profile slots. Those slots contain no identity artwork, fonts or active brand values; each stays blocked from production use until its exact sources, rights and approved direction are recorded.

See [the source and publication inventory](docs/inventory.md) for the separate direction, proof, production-readiness and publication-clearance states. `source-review-pending` on a slot means source-specific public import is not cleared; it does not change a direction selected in the local source record.

See the [maturation backlog](docs/maturation-backlog.md) for the readiness gates and ordered work to bring every customer profile from the shared foundation to reviewed delivery.

The [customer readiness guide](docs/customer-readiness.md) describes the source intake validator and six-profile coverage report.

The [build environment guide](docs/build-environment.md) records the local recipe toolchain and its preflight command.

The [versioning policy](docs/versioning-and-extensions.md) and [print capability boundary](docs/print-capability.md) explain how the shared system grows without erasing a family's composition or overstating screen proofs.

## Quick start

Use Python 3.11 or newer. Core source and contract validation has no third-party dependencies. PDF and browser review receipts, plus the one-page example, use Pillow and/or pypdf; the example also uses librsvg (`rsvg-convert`). Install the optional Python preview dependencies with `python -m pip install -e ".[preview]"`.

```sh
python -m unittest discover -s tests -v
python scripts/build_preview.py
```

The example writes an editable SVG, a vector PDF with an sRGB output intent, and hash-pinned representation/output-index records under `examples/starter/output/`.

See [the boundary and promotion rules](docs/architecture.md) before adding a source profile.

The profile-agnostic family exporter in `scripts/build_family_typesetting_suite.py` applies the same five light-context outputs to an explicit style manifest and content fixture: one-page document, two-page document, responsive web-light page, product slick, and six-page component proof. See [the typography suite notes](docs/typography-output-suite.md) for the role, accent, and verification rules.

For family-owned editorial, comic, and mark compositions, the same command also accepts [composition recipes](docs/composition-recipes.md). Recipes bind content and all 17 semantic type roles to trusted LaTeX sources, generate matching TikZ/SVG accents, and retain explicit coverage of built and missing baseline slots. The original shared layouts remain available.

Existing family-owned TeX and SVG packets can enter the same proof boundary through the [native family adapters](docs/native-family-adapters.md), which preserve their layouts and exact source bytes while recording output hashes, visual representations, and all five coverage slots.

Multiple native and recipe packets can be joined through the [family-system assembly](docs/family-system-assembly.md), which keeps visual routes, source-package identities, product variants, and baseline gaps explicit without changing family typesetting.

Connected front/back product concepts can add the [product-story audit](docs/product-story-system.md) for exact image-stage evidence, backronym identity, duplex intent, and relationships between products.

Long-form family documents can add the [document component proof](docs/document-component-proof.md), which checks page-specific evidence for contents, figures, tables, lists, equations, provenance and other components against exact PDF bytes while leaving their typesetting with the family.

Recipe `0.3.0` adds bounded concentric rings and interrupted signal rules with transparent hollow nodes. Earlier recipe versions retain their existing kind sets and native output.
