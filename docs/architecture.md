# Profile boundary and promotion rules

Each visual system owns its own profile manifest, semantic tokens, type-role bindings, asset pack, provenance record and output capability decisions. The renderer and validator are shared code; profile data and identity sources are not shared implicitly. Select an exact profile or pack ID for every build. Never search another profile as a fallback.

`profiles/registry.json` reserves six independent slots. Their `source-review-pending` status is deliberate: this public starter does not contain private artwork, corporate marks, personal identity files or unreviewed font binaries. A slot becomes usable only when its source record pins exact bytes and origin, rights and redistribution terms are documented, the approved direction is identified, and every output capability has an explicit status.

This publication status is separate from each system’s design decision, proof state and production readiness. A locally selected route remains selected even while its source files await public-release clearance. See [the inventory](inventory.md) for the current distinctions and withheld source classes.

## Common contracts

- `profile-manifest.json` defines the per-system record boundary and version.
- `asset-packs.json` keeps asset bytes, source references, rights notes and licenses together. The loader verifies hashes, rejects paths that escape the repository, and never guesses a local path for reference-only assets.
- `visual-asset-representations.json` and `visual_representations.py` distinguish editable vector masters, raster sources and derived PDFs, then check paths, hashes, dimensions, links and page mapping.
- Output capabilities remain per profile. A missing proof is represented as unavailable or not applicable after review; it is never inferred from another profile's output.

## Example boundary

The starter profile is synthetic and limited to one one-page SVG/PDF preview. `build_preview.py` loads only the starter pack, renders with librsvg, attaches an sRGB output intent, and validates its representation and proof index. It is a contract example, not a template for reconstructing an identity from a screenshot.

Keep full source packages and source-specific generators in their owning repositories. Import only approved, hash-pinned assets and the smallest adapter required by the shared renderer. Do not copy generated intermediates, contact data, or source histories into this foundation.

## Composition recipe extension

[Composition recipes](composition-recipes.md) add a declarative adapter for trusted family-owned native LaTeX. The shared build entry point selects this adapter through `recipe_version`; existing style manifests remain supported. Recipes pin their TeX entry and dependencies by SHA-256, bind plain content to escaped fields, and declare each output's geometry, context, palette, and baseline slot. They do not load executable Python plugins. The runner disables shell escape while retaining the trusted-source boundary for TeX.

Typography suite `0.5.0` makes all 17 semantic PDF font selectors follow the family's role map. Physical `body`, `display`, and `strong` remain required; `wordmark` and `mono` are optional explicit declarations. Sizes, spacing, fonts, colors, and composition remain family-owned. Shared bounded accent geometry can emit matching native TikZ and editable SVG without importing another family's artwork or identity.

The shared lockup geometry helper accepts measured row boxes and returns a connected stepped silhouette and transformed bounds. It preserves line indents instead of replacing the composition with a bounding rectangle. Families still own font measurement, spacing, fitting, and the final text transform. Separately declared PNG illustrations preserve their exact bytes and transparency in staged source, representation records, and rebuild packages; they do not become vector masters.

Image-dependent tonal fields follow the same boundary. A family samples its declared image placement into lightness and coverage grids; the shared tonal helper returns bounded circles and matching SVG/TikZ. Original images, generated vector geometry, and derived PDFs retain separate provenance. Native text effects remain trusted family-owned TeX until their rendering behavior has been proved independently.

Placement guards operate on explicitly measured polygons after scale, rotation, and translation. They preserve concave stepped spaces when checking obstacles and enforce declared regions and clearances. Family adapters must supply meaningful allocations and account for stroke extents or intended crops; the shared guard does not infer those choices from typography or artwork.

Recipe `0.2.0` adds narrative fans, registration tabs, scratch slashes, and cut keylines to the shared declarative accent path. A static registry dispatches these four kinds to their bounded native helpers; it does not import code selected by recipe data. Narrative label anchors remain metadata without family copy. The original recipe `0.1.0` continues to accept only its six kinds and preserves their native serializers. Reports hash the registry and selected helper sources, identify each backend, and distinguish generated SVG geometry from derived PDFs.

Recipe `0.3.0` adds `concentric-rings` and `signal-rule` through `technical_marks.py`, for twelve kinds. These supply transparent concentric circles and interrupted straight rules with hollow nodes. Physical checks account for complete strokes and round caps, ring separation, and lane/node clearance. The earlier versions keep their closed kind sets and native serializer bytes. Families retain copy, palette, intended-size review, and placement decisions.

Composition output names are independent of coverage. Experimental outputs have no baseline slot, and dark, white, or mixed proofs do not satisfy the five light-context baseline outputs. Machine checks produce hash-specific evidence and pending visual-review status; every changed render requires a new review. Both supported recipe versions omit font binaries from staged source and ZIP packages and record exact local font dependencies instead. See the [recipe contract](../contracts/composition-recipe.json) for the versioned source and output boundary.

An optional, separately versioned static web declaration connects family-owned HTML/CSS and explicit local assets to the same recipe build. The fixed `static_web.py` adapter validates bounded exact source bytes without importing or executing family code. Web selectors apply the same 17 semantic role bindings through family-owned `--face-*` variables. Native web source and linked PDF downloads receive separate representation metadata rather than being labeled as PDF or vector exports. Inclusion can contribute to `web-light` only at a status awaiting browser review; actual responsive behavior, keyboard interactions, and browser font selection require a separate receipt tied to those source hashes. Absent declarations preserve PDF-only behavior and `--no-web` preserves bounded PDF review.
