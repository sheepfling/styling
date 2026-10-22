# Family composition review — 2026-10-19

## Shared deliverables

All six profile slots inherit the same five light-context output slots from
[`typography-deliverable-suite.json`](../contracts/typography-deliverable-suite.json):

| Slot | Output | Shared check |
| --- | --- | --- |
| `document-one-page` | One-page PDF | Fits the approved content and keeps the family’s information hierarchy legible. |
| `document-two-page` | Two-page PDF | Preserves section flow, continuity and folios across both pages. |
| `web-light` | Responsive HTML/CSS | Uses semantic landmarks, responsive reflow, visible keyboard focus and reduced-motion rules. |
| `product-slick` | One- or two-page PDF | Communicates one product or profile story through a distinct, family-owned composition. A two-page slick can declare front/back duplex intent. |
| `component-proof` | Six-page PDF | Exercises the shared semantic components, including figures, tables, notes, references and running matter. |

Parity means each family can deliver the same formats and semantic roles. It
does not mean that every family uses one page layout, typeface, accent, or
visual motif. The 17 shared type roles are mapped to family-owned faces. The
family inputs retain their own rhythm, spacing, geometry, illustration and
special accents.

## Composition ownership

The shared exporter supplies validated document structure, PDF color checks,
web semantics and output bookkeeping. Each style manifest and content
manifest supplies the family-specific choices. Compositions can vary by
format and by family:

- A one-page sheet can prioritize a short editorial summary, an interface-like
  set of choices, a technical status page, or another source-backed sequence.
- A two-page document can extend that hierarchy while keeping continuity,
  navigation and page furniture clear.
- A web-light page can reflow for narrow screens and use interactions only
  when their keyboard and motion behavior is defined.
- A product slick can use its own frame, callouts and visual story while
  preserving the common export and provenance checks.
- The component proof checks long-form components and cross-references without
  imposing its sample order on production pages.

Use the common semantic types and validation rules as the handoff contract;
keep type selection, accent systems, artwork, shape language and layout in the
owning family’s inputs. Record unresolved sources and route decisions rather
than substituting a different family’s visual assets.

## Review boundary

The public examples are sanitized contract demonstrations. A passing suite
test establishes slot and metadata consistency; it does not approve a brand
route, source or font rights, commercial claims, accessibility, browser
behavior, or press readiness. Browser runtime is not exercised by the static
web audit. Keep those approvals and family source assets in their authorized
local records and build evidence.
