# Connected product story proofs

A connected product suite can expose needs beyond a generic `product-slick` slot: independent product names and backronyms, front/back story intent, replaceable image stages, and a narrative handoff between related tools. The [product-story contract](../contracts/product-story-system.json) adds those concepts as **proof metadata and checks**. The typography, plates, clipped frames, marks, grain, and page composition stay in the family's native TeX.

The private story manifest pins a [family-system assembly](family-system-assembly.md), then names each product's `route/output` proof. The audit re-runs that assembly, so changed PDFs, previews, native content, raster assets, or build reports invalidate the story. Each product must be a two-page proof with explicit front/back duplex intent. This validates page pairing and flip direction, while print review remains pending.

Product identity has a name, backronym, descriptor, and sequence. The initials must spell the name, and all four fields must match the pinned native content; name, backronym, and descriptor must also appear in extracted PDF text. This keeps a suite relationship in data without imposing a wordmark design. A synthetic example can use a short sequence of distinct product identities.

Each media stage binds an exact raster file from the proof's visual representations. It records a replaceable source status, a visible status label, caption bindings, `contain` fit, page, panel, inset, and separate caption box. The audit checks source dimensions and hashes, computes the image's contained size at its original aspect ratio, and rejects off-page or overlapping panel and caption allocations. Panel and caption allocations are recorded in millimeters and checked against the page bounds and one another. Each family chooses its own stage sizes and visual treatment; the shared audit only checks protected image space and source evidence.

`facets` link authored content fields to visual stages. In a synthetic example, `facets` can connect authored content fields to image stages, while `links` can describe a relationship between two products in the same suite. The shared validator checks references and exact evidence, not whether the depicted scene or technical claim is true.

```sh
python3 scripts/audit_product_story.py /path/to/private/product-story.json \
  --output /path/to/private/product-story-audit.json
```

Write the story manifest and audit report beside the family's private proof packet. New product images require updated source hashes, page proofs, and visual review. The audit does not measure image placement in the PDF, assess image subjects, verify product capabilities, or approve print production. Type treatments, artwork, and signature marks remain family-owned and are listed for human review in the family assembly.
