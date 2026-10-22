# Long-form document component proof

The six-page `component-proof` slot tests whether a family can carry a complete publication language through the shared composition runner. The shared system validates inputs and outputs; it does not draw a universal title page, contents page, table, equation or accent treatment. Those compositions remain family-owned native TeX.

The [document component proof contract](../contracts/document-component-proof.json) adds a closed, source-neutral feature plan. It covers the title page, generated contents, three-level heading hierarchy, narrative body, figures, tables, references, appendix, footnotes, running matter, informative cards, lists, highlights and underlines, equations, accent marks, and image provenance. Every feature is marked `exercised` or `not-run`. An exercised feature names its PDF pages and visible text anchors. Contents can additionally require a minimum number of internal PDF links.

Run the family recipe through the common entry point, then audit the resulting PDF:

```sh
python scripts/build_family_typesetting_suite.py \
  --style /path/to/family/component-proof/style.json \
  --content /path/to/family/component-proof/content.json \
  --output-dir /path/to/fresh-proof \
  --no-web

python scripts/audit_document_components.py \
  --plan /path/to/family/component-proof/feature-plan.json \
  --report /path/to/fresh-proof/build-report.json \
  --output /path/to/fresh-proof/feature-audit.json
```

The auditor requires the light `component-proof` output, verifies the PDF against the build report's SHA-256 and page count, checks the declared anchors on their actual pages, and counts internal PDF links. Its report pins the plan, build report and PDF hashes. A changed PDF, missing anchor, wrong page or unlinked contents entry fails. The audit status stays `checks-passed-awaiting-visual-review`; use an exact-byte [PDF review receipt](../contracts/pdf-review-receipt.json) after inspecting every rendered page.

A six-page family-owned atlas is a useful stress case for the shared audit. A synthetic packet can exercise all 17 declared type roles, native TeX, a hash-pinned image, and generated vector accents. The pages can cover a generated contents map, lists, a figure with provenance, a wrapped comparison table, a cross-referenced equation, informative cards, bibliography, appendix, footnote, and running matter. The family retains control of its copy, geometry, type sizes, artwork, palette, and page composition; the shared audit only checks declared evidence against exact PDF bytes.

This first proof does not stress a table across pages, repeated table headers, multiple figure classes, multi-line derivations, complex bibliography styles, changed-copy reflow or physical print. Those require separate specimens and review. Text anchors and link counts establish evidence presence, not typographic quality, correct attribution, accessibility or publication approval.
