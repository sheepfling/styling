# Native family proof adapters

The shared system accepts trusted family-owned TeX and SVG as first-class proof sources. Use these adapters when the family's native composition carries its identity and a common document template would change its typography, marks, spacing, or image treatment. The [adapter contract](../contracts/native-family-adapters.json) gives both routes the same source pinning, five-slot coverage report, output hashes, page previews, and pending visual-review state. It does not convert a proposed route into an approved one.

`build_native_tex_suite.py` takes a private manifest with exact SHA-256 records for every source, an sRGB ICC file, and one or more TeX entries. XeLaTeX compiles each unmodified entry with shell escape disabled. The builder checks declared page counts and sizes, required extracted text, embedded fonts, and the exact ICC bytes in the PDF OutputIntent. Its `representations.json` maps each PDF page back to its native entry and declared assets. An optional `web_source` pins historical HTML, CSS, fonts and artwork as `source-only`; it is not a validated or browser-reviewed web output. The source package remains private; native TeX is trusted source, not sandboxed by the runner. A legacy TeX packet may declare semantic roles in a style file, but this path does not claim those roles were applied unless the native TeX actually uses them.

`build_native_vector_suite.py` takes a private manifest that pins SVG pages and every linked PNG or JPEG. JPEG evidence uses visual representation `0.2.0`; existing PNG-only `0.1.0` records remain valid. It keeps the original SVG and raster files byte-for-byte under `source/`. For rendering, it writes a separate hash-recorded SVG under `render-source/` that embeds the exact declared raster bytes. This is necessary for librsvg's local-resource rules when a source SVG links to a sibling folder. The PDF and preview are rendered from that copy; the provenance record names both it and the unchanged original. A family-owned outlined SVG retains its vector geometry, but the adapter does not call its text live-editable or replace an available live-text source.

Both CLIs require a fresh output directory:

```sh
python3 scripts/build_native_tex_suite.py --manifest /path/to/private/tex/manifest.json --output-dir output/native-tex-study
python3 scripts/build_native_vector_suite.py --manifest /path/to/private/vector/manifest.json --output-dir output/native-vector-study
```

The `build-report.json` records all five baseline slots. An unselected route uses `slot: null` and remains experimental, even when its PDF renders perfectly. Selected light outputs may occupy PDF baseline slots only at `built-awaiting-visual-review`; historical web can be `source-only`, and is `not-run` when absent. It advances only after its own static and browser evidence. Each reviewed output still needs a current [family-character review receipt](customer-readiness.md). Native SVG rendering is a screen proof, not a print production export.

The adapters deliberately leave family composition in its original source. Reconcile newer source packets by hash and visually compare their actual-size proofs before migrating them; an older archive does not establish the latest route or approval state.
