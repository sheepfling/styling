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
