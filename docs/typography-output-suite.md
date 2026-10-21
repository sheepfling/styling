# Shared typography output suite

The suite contract gives every profile the same light-context handoff while keeping family-specific typography, identity, artwork, accents, geometry, source content, rights, and approval state in its own inputs.

## Required slots

Each of the six profile slots uses the same five light-context outputs:

- `document-one-page`: one-page PDF brief.
- `document-two-page`: two-page PDF with continuity and folios.
- `web-light`: responsive static HTML/CSS page.
- `product-slick`: one- or two-page PDF product or profile story.
- `component-proof`: six-page PDF that exercises shared semantic document components.

The component proof exercises shared semantic structure such as headings, narrative, tables, figures, notes, cautions, specifications, examples, references, appendix, footnotes, and running matter. It is a required shared slot; each family applies its own type, identity and accents.

A two-page product slick can represent the front and back of one sheet. A [composition recipe](composition-recipes.md) records that intent explicitly with the optional per-output `duplex` object: schema version `0.1.0`, `flip: "long-edge"` or `"short-edge"`, `front_page: 1`, and `back_page: 2`. Both pages keep the declared dimensions and upright orientation; the report preserves the sheet and face map. Two-page articles and reader spreads do not acquire duplex intent automatically. The declaration does not impose pages, configure a printer, or establish physical print approval.

The common semantic vocabulary names 17 type roles. Every family input maps each role to its own physical face IDs (`body`, `display`, `strong`, and `wordmark`). An unresolved family may use a neutral face for layout metrics only if its input records that the face is not selected.

## Build and review

The bounded builder consumes a family-owned style manifest and content manifest. It uses the repository's Tectonic/Poppler toolchain, attaches the supplied sRGB screen-proof profile, and writes PDFs, static web source, an editable source package, and a build report to a private output directory.

```sh
python scripts/build_family_typesetting_suite.py \
  --style /path/to/family/style.json \
  --content /path/to/family/content.json \
  --output-dir /path/to/private-output
```

The build checks declared source hashes, page counts, embedded fonts, required copy, cross-references, and the exact ICC profile bytes in the PDF catalog. The static web audit checks semantic landmarks, local references, responsive rules, keyboard focus, reduced-motion handling, and all semantic role selectors. It does not launch a browser; browser verification remains a separate status.

Install the optional preview dependencies (`pypdf` and Pillow) with `python -m pip install -e ".[preview]"`. The build also requires Tectonic, Poppler's `pdfinfo`, `pdftotext`, and `pdffonts`, and `rsvg-convert` when a source logo or accent is SVG.

The contract establishes structural parity only. It does not select a route, grant source or font rights, verify commercial claims, certify accessibility or press readiness, or approve release. Record missing assets and unverified behavior explicitly in the family recipe and build evidence.
