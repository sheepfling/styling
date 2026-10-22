# Shared styling system maturation backlog

This backlog turns the current shared styling foundation into a dependable system that can onboard and serve every customer without sharing their identity sources. It tracks platform readiness and profile readiness separately. Customer names, private assets, font files, and source-specific approvals stay in each customer's authorized records. Shared architecture must preserve the expressive typography and composition of each family; a common output contract is not a common visual template.

## Maturity gates

| Gate | Evidence required |
| --- | --- |
| Foundation | Versioned shared contracts and builders exist; synthetic fixtures exercise the documented boundaries. |
| Profile-ready | One customer has an exact source and rights record, selected typefaces and route, and a declared capability plan. |
| Reviewed pilot | Agreed outputs build from pinned inputs; every delivered page has a current visual review tied to its hashes and to the family's intended visual character. |
| Customer-ready | The customer's committed output set has current evidence, unresolved capabilities are explicit, web behavior is browser-reviewed where offered, and the customer has approved the direction, claims, and family-specific typesetting. |
| Production-ready | Supported build environments, compatibility policy, operational documentation, and repeatable release checks are in place for the capabilities offered. Print production is a separate capability gate. |

Report each profile's gate and the evidence behind it. Report the six-profile portfolio as a distribution, with the least-ready active profile visible; an average must not hide a customer that has not been onboarded.

## Backlog

Items are unassigned. `P0` closes current readiness ambiguity; `P1` makes real customer pilots repeatable; `P2` hardens the system for broad, sustained use. The status notes below describe implementation progress, not customer approval.

### P0 — Make readiness legible

#### MAT-001 — Reconcile the public contract and guide text

**Status:** Implemented locally; contract-linked guide check added.

Update composition and typography docs to match the live contracts, including one- or two-page product slicks and the optional `mono` physical face. Remove stale descriptions and add a small check that catches the documented contract values drifting again.

**Acceptance:** every documented output page count, type-face rule, recipe version, and review status agrees with its source contract; the documentation check passes in the normal repository validation command.

#### MAT-002 — Define a customer source and rights intake record

**Status:** Implemented locally with a synthetic intake and validator; customer-specific records are still needed.

Create a profile-owned intake template for exact asset origins and hashes, font identity and license, redistribution limits, approved design direction, source owner, claim sources, and publication status. Preserve separate states for design approval, local proof, production readiness, and public-release clearance.

**Acceptance:** a synthetic profile can complete the template without ambiguous status values; the profile validator rejects missing origins, unpinned source bytes, invalid status transitions, and unsupported rights claims. Private customer inputs remain outside the public repo unless cleared.

#### MAT-003 — Add a portfolio coverage report

**Status:** Implemented locally for six neutral profiles and their 30 slots; private evidence is not yet supplied.

Produce a customer-neutral report for the six profile slots showing each required output, latest input/output hashes, proof and review status, and explicit gaps. Keep static web checks separate from browser evidence and screen proofs separate from print approval.

**Acceptance:** the report distinguishes `not-started`, `built-awaiting-review`, reviewed, unavailable-with-reason, and approved states; it never counts an unreviewed or dark-context experiment as a completed light baseline slot; portfolio summaries show every profile rather than only a total.

#### MAT-012 — Protect distinctive family typesetting

**Status:** Principle and exact-byte family-character review gate implemented locally; older benchmark packets inspected. Before/after comparison against the latest family sources remains open.

Record a family-owned visual brief and reference proof before adapting it to shared architecture. The review should call out its type hierarchy, marks, page rhythm, deliberate asymmetry, accents, image treatment, and any native text effects. Shared contracts may constrain evidence and safety, but must leave those visual decisions with the family.

**Acceptance:** an architecture change that touches composition carries before/after proofs at intended size for at least one expressive family. Reviewers can point to preserved signature features and identify any lost character. A family may retain its own trusted LaTeX layout or special mark implementation where a generic primitive would flatten the work.

### P1 — Make customer pilots repeatable

#### MAT-004 — Establish the first full customer profile as a reference pilot

Run one authorized customer profile from source intake through its agreed shared output set. Use an existing local design and builder pilot to test the full customer path, including rights, approved type, claims, capability decisions, and preservation of its visual character.

**Acceptance:** the profile has pinned sources, exact font records, a selected route, explicit output coverage, per-output visual-review receipts, and a reproducible package. No customer data is copied into synthetic fixtures or public examples without clearance.

#### MAT-005 — Add browser review for declared web outputs

**Status:** Exact-byte browser receipt format and validator implemented locally; automated observation and customer-site review remain open.

Use a supported browser automation environment to inspect each offered viewport, computed typefaces, responsive reflow, contrast, keyboard focus and interaction behavior, reduced motion, and local links. Attach the receipt to the exact HTML, CSS, and asset hashes.

**Acceptance:** a web output cannot be marked customer-ready from static checks alone; the browser receipt records browser/version, viewports, results, and reviewed source hashes. Failed checks remain actionable and visible.

#### MAT-006 — Formalize the visual review receipt

**Status:** A new exact-byte PDF receipt validator is implemented locally; migration of older review records and web review remain open.

Standardize a review record for PDF pages and other visual outputs, including reviewer, date, exact artifact hashes, intended use/size, findings, corrected issues, and remaining limits. Make changed bytes invalidate the prior receipt.

**Acceptance:** a validator confirms the receipt matches current artifacts and required page coverage; stale or incomplete receipts cannot advance a profile's proof status.

#### MAT-013 — Exercise the architecture against three mature family studies

**Status:** Private family packets have been exercised through native TeX, SVG, and recipe reports. A route-aware family assembly audits exact source/output bytes and exposes signature-feature checklists and baseline gaps. The connected product-story audit binds front/back identity, duplex intent, replaceable media stages, concept facets, and cross-product links to pinned proofs. Newer source reconciliation, web migration, semantic-role review, and human before/after signoff remain open.

Use the existing distinct family studies as stress cases for the same output contract. Compare their native outputs and chosen marks before and after shared integration. Record what belongs in reusable geometry, what remains a family-owned macro or artwork source, and what the shared system still cannot express cleanly.

**Acceptance:** each study retains its own typography, identity accents, and page composition in reviewed outputs. Any shared change that helps one family while dulling another is revised or kept local; no profile is considered mature solely because its five slots have files.

#### MAT-014 — Prove long-form document components without a common page template

**Status:** A six-page local screen proof and exact-byte component audit are complete; broader stress cases and cross-family migration remain open.

Use a family-owned native composition to exercise the common `component-proof` slot: title and generated contents, three heading levels, body, image/figure/caption/provenance, wrapped table, list styles, footnote, mirrored running matter, bibliography and appendix, informative cards, highlights, underlines, equation numbering and accent marks. Record page-level feature evidence against the exact PDF while preserving the family's type and page rhythm.

**Acceptance:** six pages build through the shared runner; generated links and references resolve; every page receives a hash-bound visual review; a changed PDF invalidates the feature audit. Follow with a table that truly spans pages with repeated headers, more demanding math and changed-copy reflow, then repeat the approach in a second expressive family. Text-anchor checks alone do not count as visual approval.

#### MAT-007 — Pin and document the build environment

**Status:** Local toolchain diagnostic and reference environment documented; repeatable CI image remains open.

Declare supported Python, XeLaTeX/Tectonic where applicable, Poppler, image libraries, and font-resolution behavior. Provide a clean setup path and a diagnostic command that reports missing or incompatible tools before lengthy builds.

**Acceptance:** a new developer can build the synthetic examples in a clean supported environment using documented commands; build evidence records relevant tool versions; private font files remain external and are checked against declared hashes.

### P2 — Operate and extend the system safely

#### MAT-008 — Add continuous integration and release checks

**Status:** Public CI workflow drafted locally with native recipe integration; first hosted run and release packaging remain open.

Run the public contract and renderer tests on supported environments, plus synthetic end-to-end build smoke checks. Publish a versioned release process for the shared contracts and helpers.

**Acceptance:** pull requests run the required checks; release artifacts identify the contract and tool versions; failures block a release; private profiles, generated proofs, and font binaries are absent from public packages by default.

#### MAT-009 — Define compatibility and migration policy

**Status:** Versioning and design-preserving migration policy documented; an active-package migration inventory remains open.

Document which changes require a recipe or suite version bump, how deprecated versions are supported, and how customer packages migrate without changing old output semantics unexpectedly.

**Acceptance:** each supported recipe version has a fixture and compatibility evidence; version-specific grammar changes reject unsupported fields and kinds; migration notes identify changed outputs and required re-review.

#### MAT-010 — Declare the print-production capability boundary

**Status:** Handoff requirements and independent print gate documented; press export and printer proof remain open.

Decide which customers need press-ready output. For those who do, define trim size, bleed, safe area, duplex/imposition expectations, color profile, raster resolution, and printer handoff evidence as a distinct print capability.

**Acceptance:** a print-ready claim requires a reviewed press export and printer-specific handoff checks. Screen proofs and duplex metadata alone cannot satisfy the gate. Customers without print needs can mark the capability unavailable or not applicable with a reason.

#### MAT-011 — Define bounded extension and review rules

**Status:** Shared extension policy documented; the next proposed primitive must demonstrate it against a real family.

Keep new shared marks and render capabilities explicit, bounded, versioned, and family-neutral. Require a real customer use case and evidence that a new primitive belongs in shared architecture rather than a family's private source. Shared geometry should enable an expressive treatment, not dictate the treatment.

**Acceptance:** a proposed extension includes contract changes, limits, compatibility behavior, native output evidence, tests, documentation, and an example that uses synthetic content; customer-specific copy, assets, and identity choices remain in the profile.

## Current baseline

The public registry currently has six generic profiles marked `source-review-pending`, one synthetic starter proof, and no public customer proofs. Existing private family studies demonstrate more expressive typesetting than the synthetic fixture and remain the design benchmark. MAT-001 through MAT-003 now have local implementations; next validate them with an authorized customer pilot and use MAT-012/MAT-013 to guard visual quality as the shared system grows.
