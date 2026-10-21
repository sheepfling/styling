# Declarative composition recipes

A composition recipe connects a family's native LaTeX layout to the shared typography, accent geometry, build checks, and output evidence. The family owns the fonts, palette, copy, layout source, and provenance. The shared runner owns input validation, generation of semantic selectors and escaped content macros, compilation, PDF checks, previews, and packaging.

The recipe contract is [composition-recipe.json](../contracts/composition-recipe.json), current version `0.3.0`, with `0.1.0` and `0.2.0` still supported. The version selects an explicit accent grammar; it does not change the existing style-manifest adapter. Selecting a recipe does not copy another family's identity or make its source public.

## Build through the shared entry point

```sh
python scripts/build_family_typesetting_suite.py \
  --style /path/to/sample-family/recipe.json \
  --content /path/to/sample-family/content.json \
  --output-dir /path/to/private-output/sample-v1 \
  --only opening-panel \
  --only accent-study \
  --no-web
```

The entry point dispatches to the composition runner when the style input declares `recipe_version`. `--only` is repeatable and accepts any output ID declared by that recipe. IDs use lowercase kebab case; selections must be unique and non-empty. Omitting `--only` builds every declared recipe output. Choose a new output directory for each build; the runner rejects an existing destination.

Recipes `0.1.0`, `0.2.0` and `0.3.0` build PDFs with XeLaTeX and render every page with Poppler. They require `xelatex`, `pdfinfo`, `pdftotext`, `pdffonts`, `pdftoppm`, and the optional Python `pypdf` dependency. Recipes declaring raster assets also require the optional `Pillow` dependency. An optional `web` declaration stages exact native static web sources and runs source checks; the browser review remains separate. The existing style-manifest adapter retains its own PDF and static web behavior.

## Manifest and source boundary

The top level declares `recipe_version`, `family_id`, `display_name`, `status`, `type`, `role_map`, `palettes`, `srgb_icc`, `bundle_fonts`, and `outputs`. `output_dir` is optional when supplied on the command line. Content lives in a separate plain JSON object.

Each output has its own native `.tex` entry and a list of `.tex` or `.sty` dependencies. Every source record contains exactly `path` and lowercase `sha256`. Source paths resolve relative to the recipe directory, retain their declared tree when staged, and cannot traverse parent directories or use symlinks. The runner verifies those hashes before staging. The RGB ICC profile is also an explicit recipe-relative file; build evidence records its staged bytes and checks the PDF's exact embedded profile.

TeX is trusted local source. Compilation disables shell escape; it does not provide a sandbox for arbitrary TeX. Recipes select files and data and do not import executable Python plugins. Changes to source files require updating the corresponding hash in the recipe.

`type` declares local font files with their SHA-256 hashes. Paths may be absolute or recipe-relative and must resolve to existing TTF, OTF, or TTC files with TeX-safe paths. All recipe versions require `bundle_fonts: false`: staged source and the editable ZIP omit font binaries. Reports preserve the required font paths and hashes, so recompilation needs those exact local fonts. Font selection and redistribution permission remain separate family decisions.

## Semantic typography

[Typography suite `0.5.0`](../contracts/typography-deliverable-suite.json) requires all 17 semantic roles. Every role maps to one declared physical face. `body`, `display`, and `strong` remain required; `wordmark` and `mono` are optional. An optional face has no automatic fallback: a profile without it maps the relevant semantic role to another declared face.

| Semantic roles | Generated selectors |
| --- | --- |
| `identity.wordmark` | `\TypeIdentityWordmark` |
| `document.kicker`, `document.eyebrow` | `\TypeDocumentKicker`, `\TypeDocumentEyebrow` |
| `document.title`, `document.subtitle`, `document.lead` | `\TypeDocumentTitle`, `\TypeDocumentSubtitle`, `\TypeDocumentLead` |
| `section.heading`, `section.marker` | `\TypeSectionHeading`, `\TypeSectionMarker` |
| `body`, `body.strong` | `\TypeBody`, `\TypeBodyStrong` |
| `label`, `data.numeric`, `data.axis` | `\TypeLabel`, `\TypeDataNumeric`, `\TypeDataAxis` |
| `card.title`, `caption`, `annotation`, `footer` | `\TypeCardTitle`, `\TypeCaption`, `\TypeAnnotation`, `\TypeFooter` |

The selectors bind to `\BodyFace`, `\DisplayFace`, `\StrongFace`, `\WordmarkFace`, or `\MonoFace` according to `role_map`. Layout source uses the semantic selector for each exercised role. Changing a mapping changes the generated font selector without editing the composition. Selectors set the font family only; the family layout controls sizes, leading, spacing, color, and placement. Declaring all 17 mappings does not establish that every role appears in a particular output.

For a recipe web proof, `css_role_definitions(role_map, type)` emits `[data-type="document.title"] {font-family: var(--face-display);}` and the other 16 bindings according to the same map. Include these generated rules in a declared linked CSS source before pinning its hash. The family defines each exercised `--face-*` variable from its own local font alias and fallbacks. The static checker verifies those binding clauses; browser evidence establishes computed font selection.

## Optional native static web proof

The independent web source schema `0.1.0` works with every supported accent grammar. Add a top-level declaration such as:

```json
"web": {
  "schema_version": "0.1.0",
  "id": "web-light",
  "context": "light",
  "palette": "paper",
  "entry": {"path": "web/index.html", "sha256": "<64 lowercase hex characters>"},
  "dependencies": [
    {"path": "web/styles.css", "sha256": "<64 lowercase hex characters>"},
    {"path": "web/assets/mark.svg", "sha256": "<64 lowercase hex characters>"},
    {"path": "web/assets/brief.pdf", "sha256": "<64 lowercase hex characters>"}
  ],
  "required_text": ["cover.title", "cover.summary"],
  "viewports": [
    {"width": 390, "height": 844},
    {"width": 768, "height": 1024},
    {"width": 1440, "height": 1000}
  ]
}
```

Remove `--no-web` to include it through the shared CLI. `--only` selects PDFs independently; web inclusion follows the web flag. With no web declaration the recipe retains its PDF-only behavior. All declared inputs validate before output creation, including when omitted from a bounded PDF build. The `--no-web` rebuild recipe removes the omitted web declaration so that it has no dangling source dependencies.

The declaration accepts exactly its listed fields. Entry and dependency records pin safe recipe-relative paths and SHA-256 hashes. Dependencies must stay inside the entry's directory. The runner stages that tree under `web/` and preserves the original source paths under `recipe-input/`. It accepts 1–64 dependencies: CSS, passive SVG, PNG, and linked PDF documents. Text sources have a 1 MiB limit; PNG and PDF files have an 8 MiB limit; all web source totals at most 16 MiB. PNG geometry must be at most 8192 pixels per dimension. PNG and PDF signatures classify source bytes; successful image/document rendering requires separate review.

HTML must explicitly balance its elements, declare language, UTF-8 and a device-width viewport, contain exactly one title, h1 and main, and provide header, nav and footer landmarks. Required content references must occur in body text; images need an explicit `alt`. Local file references must resolve within the declared files, and same-document fragments must resolve to unique ids. Scripts, inline styles, active SVG, CSS imports/escapes, font binaries, and remote, data, query or parent-traversing references are outside this source subset. Existing native SVG accent exports work as explicit pinned assets; local PDF downloads retain their own exact bytes.

Linked CSS must apply every semantic role from `role_map`, define its family-owned physical-face variables, and contain focus-visible, responsive width and reduced-motion media rules. Declare 3–8 intended viewport dimensions, with distinct integer widths including mobile at most 480 CSS pixels and desktop at least 1200; widths span 320–2560 and heights 480–2160. These are static signals and intended dimensions. They do not establish responsive layout, contrast, keyboard order, accessibility, or actual browser fonts.

`web-representations.json` records native HTML/CSS/SVG/PNG sources and linked PDF documents, separate from the existing PDF-only `representations.json` grammar. The build report records exact source hashes, origins and intended viewports. A light-context proof contributes to `web-light` only at `static-checks-passed-awaiting-browser-review`; attach a separate browser receipt to the exact reviewed bytes. The runner does not execute family code, publish a site, or distribute font binaries.

## Output declarations and native TeX

This synthetic excerpt illustrates one entry in `outputs`; the complete recipe also needs its top-level declarations and all 17 role bindings. Replace the hash placeholder with the exact entry's SHA-256.

```json
{
  "opening-panel": {
    "slot": null,
    "context": "light",
    "palette": "paper",
    "page_count": 1,
    "page": {"width_mm": 210, "height_mm": 148},
    "entry": {"path": "latex/opening.tex", "sha256": "<64 lowercase hex characters>"},
    "dependencies": [],
    "bindings": {"Title": "cover.title", "Summary": "cover.summary"},
    "required_text": ["cover.title", "cover.summary"],
    "accents": {
      "Motion": {
        "kind": "motion-bars",
        "width_mm": 44,
        "height_mm": 12,
        "parameters": {"count": 4, "slant": 0.35}
      }
    }
  }
}
```

`bindings` keys contain PascalCase letters only. Their values resolve dotted object keys or list indexes, such as `cover.title` or `sections.0.title`, to non-empty plain strings. The runner escapes these strings for TeX and creates `\FieldTitle` and `\FieldSummary`. `required_text` names content paths that must appear in extracted PDF text; it is a separate check from declaring a binding.

Each named palette supplies exactly `page`, `ink`, `muted`, `accent`, and `line` as six-digit RGB hex colors. The generated file defines `BGPage`, `BGInk`, `BGMuted`, `BGAccent`, and `BGLine`, plus their shorter aliases. Output context is declared separately from palette choice.

An optional `duplex` declaration identifies a two-page PDF as the front and back of one sheet. For example, add this field to an output with `page_count: 2`:

```json
"duplex": {
  "schema_version": "0.1.0",
  "flip": "long-edge",
  "front_page": 1,
  "back_page": 2
}
```

The object accepts exactly these four fields. `flip` is `long-edge` or `short-edge`; front and back must be the integer page numbers 1 and 2, respectively. The declaration works with every supported recipe version and any otherwise valid PDF slot, including an experimental `null` slot. A two-page product slick is a typical use; an ordinary two-page article does not imply duplex.

The runner checks both pages against the declared dimensions and rejects unexpected rotation as usual. It preserves the authored declaration in `recipe-input/style.json`. The PDF's `checks.duplex`, its per-output `duplex` report entry, and `rebuild_recipe.duplex[output-id]` record the declaration plus `sheet_count: 1`, `page_faces` mapping pages 1/2 to front/back of sheet 1, `imposition: "none"`, and `physical_print_review: "pending"`. Outputs without this optional field retain their prior report and rebuild behavior.

This records intended front/back pairing and a printer flip setting. It does not impose or rotate pages, configure a printer, add bleed, or establish physical print approval. The family owns any visible FRONT/BACK labels and the design of each face; both remain upright in the native PDF.

The native entry loads `generated.tex` after `fontspec`, `xcolor`, and `tikz`, and calls `\SrgbIntent` after the document begins. For the excerpt above, a small entry could be:

```tex
\documentclass{article}
\usepackage[paperwidth=210mm,paperheight=148mm,margin=14mm]{geometry}
\usepackage{fontspec,xcolor,tikz}
\input{generated.tex}
\pagestyle{empty}
\begin{document}
\SrgbIntent
\pagecolor{BGPage}\color{BGInk}
{\TypeDocumentTitle\fontsize{30}{32}\selectfont\FieldTitle\par}
\vspace{5mm}
{\TypeBody\fontsize{12}{16}\selectfont\FieldSummary\par}
\vfill
\noindent\AccentMotion
\end{document}
```

The entry owns page geometry; declared dimensions and page count are checked against the compiled PDF. Dimensions must be 50–500 mm, and a recipe output may contain at most 32 pages. List every family source dependency explicitly so the staged source is reviewable and reproducible.

## Original raster illustrations

An output may declare an optional `assets` list alongside `entry` and `dependencies`. Omitting the list keeps existing recipes valid. Each record contains exactly a manifest-relative `path` and lowercase `sha256`:

```json
"assets": [
  {"path": "art/engravings/planet.png", "sha256": "<64 lowercase hex characters>"}
]
```

The runner accepts readable PNG files, including transparency. It checks their hashes, dimensions, encoded color mode, safe paths, and absence of symlinks before creating the output directory. JPEG support is deferred until the shared visual representation validator supports it. Asset destinations cannot duplicate entries, dependencies, other assets, or reserved generated files and compile directories.

The PNG retains its declared tree in each output's editable source and in `recipe-input`. A native entry can load `graphicx` and place `\includegraphics{art/engravings/planet.png}` within its layout. Original illustrations supply image detail; typography, page structure, marks, and TikZ accents remain separately editable. An illustration is recorded as a raster source with `no-vector-master` status rather than described as vector geometry.

Every declared asset is hash checked, staged, included in PDF source hashes and origins, and packaged in the editable ZIP, even if the entry does not place it. `representations.json` records each output's staged raster bytes and metadata with a unique representation ID. The rebuild recipe preserves the asset declarations. Font binaries remain external dependencies.

## Bounded comic accents

[accent_registry.py](../src/sheepfling_styling/accent_registry.py) statically dispatches the explicit versioned grammar. Recipe `0.1.0` accepts the six original [comic_accents.py](../src/sheepfling_styling/comic_accents.py) primitives below and rejects the newer kinds. Recipe `0.2.0` accepts all six with the same native serializer bytes, plus `trajectory-fan`, `registration-tab`, `scratch-slashes`, and `cut-keyline`. Families choose their parameters, palette, scale, and placement. Accent data never selects executable code or a family asset fallback.

| Kind | Possible compositional job | Main parameters |
| --- | --- | --- |
| `motion-bars` | Signal progression or a reading direction | `count`, `slant` |
| `crosshair` | Locate a point or orient a label | `radius_ratio` |
| `halftone` | Establish a tonal region or edge | `columns`, `rows`, `dot_min_mm`, `dot_max_mm`, `fade` |
| `burst` | Bring forward a brief callout | `rays`, `inner_ratio`, `rotation_degrees` |
| `orbit` | Connect or group related ideas | `rings`, `tilt_degrees` |
| `caption-frame` | Delimit a supporting caption | `cut_mm` |

Each recipe contains `kind`, `width_mm`, `height_mm`, and `parameters`; named output accents become `\Accent<Name>` macros. The six original kinds have width bounds of 6–160 mm and height bounds of 6–100 mm. All parameters are validated, including finite numeric values, integer counts, kind-specific bounds, and an optional `stroke_mm` of 0.08–1.5 mm. Unknown fields and parameters are rejected. Halftone dot radii are further capped to preserve separation at the declared pitch. Narrative and finish kinds use their own physical bounds rather than inheriting these six-kind limits.

SVG and TikZ consume the same deterministic geometry and clip to the declared box. The PDF uses native TikZ; each accent also exports an editable SVG under `accents/<output-id>/<Name>.svg`. The build report records the explicit grammar version, normalized recipe, fixed backend, and any label anchors. Source evidence hashes the registry and selected helper modules. Representation metadata identifies the actual SVG serializer with the recipe and output hash. It is not a claim that the PDF linked the SVG or that the accent establishes an identity mark.

## Narrative fans and registration tabs

[narrative_marks.py](../src/sheepfling_styling/narrative_marks.py) supplies `trajectory-fan` and `registration-tab` geometry. Both are accepted directly in recipe `0.2.0` `accents`. Recipe `0.1.0` retains its six-kind boundary; a family continuing on that version can still generate native TeX during authoring and pin it as a trusted dependency. SVG and TikZ consume the same immutable primitive stream.

```python
from sheepfling_styling.narrative_marks import narrative_mark, tikz_narrative_mark

fan = narrative_mark({
    "kind": "trajectory-fan", "width_mm": 60, "height_mm": 36,
    "parameters": {"arms": 4, "stroke_mm": 0.3, "node_radius_mm": 0.9},
})
native_tex = tikz_narrative_mark(fan)
```

Dimensions are 16–180 mm wide and 16–120 mm high; strokes are 0.25–1.5 mm. Fans accept three to five arms and hollow terminal radii of 0.6–2.5 mm. Tabs accept a corner cut, index-rail width, and registration radius. Geometry-dependent limits preserve node gaps and keep full strokes inside the field. Export validation checks primitive coordinates and label-anchor metadata as well as the normalized recipe.

Coordinates use positive y upward. TikZ binds to `BGInk`, `BGPage`, `BGAccent`, and `BGLine`; SVG requires those four colors as an explicit `ink`/`page`/`accent`/`line` hex palette. Label anchors carry position and alignment only. Families own the actual labels, type measurement, surrounding clearances, context, and any identity decision. A generated tab or fan does not select a logo or establish small-print suitability.

For direct declarative use, set the top-level `recipe_version` to `0.2.0` and add ordinary named accents:

```json
"accents": {
  "Fan": {"kind": "trajectory-fan", "width_mm": 60, "height_mm": 36, "parameters": {"arms": 4}},
  "Tab": {"kind": "registration-tab", "width_mm": 60, "height_mm": 24, "parameters": {}},
  "Scratch": {"kind": "scratch-slashes", "width_mm": 50, "height_mm": 18, "parameters": {}},
  "Keyline": {"kind": "cut-keyline", "width_mm": 60, "height_mm": 36, "parameters": {}}
}
```

These become `\AccentFan`, `\AccentTab`, `\AccentScratch`, and `\AccentKeyline`. No generated native dependency file is needed for these four declarations. Narrative label anchors remain report metadata; they do not place labels automatically.

## Comic finish geometry

[comic_finishes.py](../src/sheepfling_styling/comic_finishes.py) supplies recipe `0.2.0` kinds `scratch-slashes` and `cut-keyline`. Scratches accept width 8–180 mm, height 6–120 mm, `count`, `slant`, `strength`, `mode`, `cut_style`, and `stroke_mm`. `cut_style: "straight"` produces four-point slots with parallel straight edges. The default `"bent"` preserves earlier recipes' six-point paths. The default `auto` mode becomes clean below 24 mm width or 10 mm height; zero strength is also clean. Explicit `scratched` mode remains a deliberate family choice. Cut keylines accept width 16–180 mm, height 12–120 mm, `inset_mm`, `cut_mm`, `break_mm`, `echo`, and `stroke_mm`, with additional checks against collapsed frames and escaped stroke bounds.

Both kinds are bounded vector accents, with matching TikZ/SVG from native geometry. Scratches use real transparent cuts rather than page-colored patches. They remain separate from typography distress: using a scratch accent does not alter glyph contours or clip text. A family still owns placement, copy, palette, clearance, and review at the intended size; neither kind selects an identity treatment.

## Concentric rings and interrupted rules

Recipe `0.3.0` adds two kinds through [technical_marks.py](../src/sheepfling_styling/technical_marks.py), for twelve total. Versions `0.1.0` and `0.2.0` reject them and retain their existing geometry. Both new kinds serialize one immutable native circle/line stream to TikZ and SVG. Circles have no fill, so artwork or color beneath their centers remains visible.

`concentric-rings` accepts width/height 8–160 mm, `rings` (3–8), `inner_ratio` (0.12–0.5), and `stroke_mm` (0.15–1.2). The circles share a center and preserve at least 0.2 mm air between complete strokes. Invalid combinations at small sizes reject rather than silently reducing the ring count.

`signal-rule` accepts width 20–180 mm, height 6–48 mm, `lanes` (1–3), `node_radius_mm` (0.6–2.5), `gap_mm` (0.5–6), and `stroke_mm` (0.15–1.2). Each lane alternates its hollow node between the right and left quarter positions. Two straight rule segments stop short of the circle; the declared gap is measured between visible strokes, including round caps. Nodes, lane spacing and remaining rule lengths are checked in physical units. Labels and any surrounding plaque remain family-owned live typography and layout.

## Image-dependent tonal fields

[tonal_halftone.py](../src/sheepfling_styling/tonal_halftone.py) accepts a rectangular grid of normalized lightness values and optional coverage values. The family adapter owns image decoding, alpha compositing, physical crop/placement, sample filtering, color interpretation, and the transition envelope. The shared helper owns finite-value validation, area-scaled dot geometry, physical bounds, and matching native SVG/TikZ serialization. It never edits an image, selects artwork, or assumes a family palette.

`tonal_halftone(tones, width_mm=..., height_mm=..., coverage=...)` returns immutable circles in millimetres. Input rows run from top to bottom; returned geometry uses y-up coordinates. Darker samples produce larger dots; zero coverage and white samples emit none. Coverage scales the squared radius, so it changes ink area. The radius cap preserves separation at the cell pitch. Each field accepts at most 64 rows, 64 columns, and 1,200 samples. `svg_tonal_halftone(field, color)` requires an explicit hex ink color; `tikz_tonal_halftone(field)` uses `BGInk` and one grouped path without PGF math loops.

`corner_halftone(width_mm=..., height_mm=..., corner="bottom-right")` generates a synthetic two-axis dissolve using the same immutable stream and exporters. Four page-coordinate corners are supported. The bounded grid defaults to 32 by 32; normalized corner distance drives smoothstep coverage and therefore dot area. `fade_radius_ratio` (0.25–1.5) controls its reach. Families own palette, placement, and clipping. This helper is an authoring factory, not a new recipe accent kind: pin its generated TeX as a trusted dependency and record its producer hash and SVG geometry. These designed fields have no sampled-image origin.

Keep the original image and generated geometry distinct. Record the exact original bytes, crop transform, sampling method, coverage grid, producer hash, and generated file hashes. An SVG dot field is generated vector geometry with a raster sampling origin; it is not a vector reconstruction of the original illustration. A family can pin the generated native `.tex` field as a composition dependency. Physical print, tone matching, and seamless compositional transitions still require their own review.

## Measured stepped lockups

[lockup_geometry.py](../src/sheepfling_styling/lockup_geometry.py) provides geometry for stacked display text whose lines have different widths and indents. The family supplies one to eight measured row boxes using `x_mm`, `y_mm`, `width_mm`, and `height_mm`. `measure_lockup` adds explicit padding, traces the connected rectangle union without losing its steps, and returns untransformed and rotated polygons plus their total bounds. An optional offset shadow participates in those bounds. Disconnected rows, point contacts, non-finite values, and unsupported dimensions are errors.

Coordinates use positive y downward; a positive angle rises to the right. `polygon_tikz` emits a closed path with explicit millimetre units, suitable for a `yscale=-1` scope. Use the returned transformed polygon when rotation is already applied to the points, or rotate the original polygon in the renderer, once. The helper does not measure fonts, fit copy, create perspective, or choose an identity face. Family authoring code can generate a `.tex` dependency from these polygons and pin it in the recipe like any other native source.

## Placement regions and clearances

[composition_bounds.py](../src/sheepfling_styling/composition_bounds.py) scales, rotates, and translates simple measured polygons with `transform_outline`. `guard_placement` checks the result against an explicit rectangular region and up to 64 rectangular obstacles. It checks actual polygon intersections, so a quiet region inside a stepped notch does not fail merely because bounding boxes overlap. A declared clearance shrinks the usable region and expands obstacles; region-edge contact at that clearance is allowed, while obstacle contact is rejected.

The helper rejects malformed, degenerate, self-intersecting, and non-finite geometry. It reports transformed bounds and specific failed regions or obstacles. Families own the measured outlines, placement controls, intended underlaps, stroke padding, and region definitions. Guarded allocation boxes do not establish accurate font outlines, complete page collision detection, or a projective transform. Keep deliberate oversized/cropped artwork separate from guarded text allocations and exercise rejected scale/rotation cases in authoring evidence.

## Coverage and review evidence

Output IDs are composition names. `slot` connects an output to one of the shared PDF baseline slots, or is `null` for an experimental output. A declared slot must match its page-count contract: one page for `document-one-page`, two for `document-two-page`, one or two for `product-slick`, and six for `component-proof`.

Only selected, machine-checked outputs with `context: "light"` contribute to baseline coverage. A light experiment with a null slot remains an experiment. Dark, white, and mixed contexts remain additional outputs and do not close the five light-context baseline gaps. Included light-context native web source has its own static-checks-passed status awaiting browser review; absent or omitted web source leaves `web-light` explicitly `not-run`.

The build produces PDFs, per-page PNG previews, staged editable sources, an editable ZIP, `build-report.json`, and `representations.json`. Evidence includes exact input and output hashes, tool versions, declared font dependencies, extracted-copy checks, page counts and dimensions, embedded fonts and Unicode maps, TeX layout diagnostics, and the exact sRGB output intent. A failed build records `rejected`; completed machine checks record `checks-passed-awaiting-visual-review` with per-output review still `pending`.

Review every rendered page. Keep separate visual-review evidence tied to the exact PDF and preview hashes being inspected, including findings and any remaining limitations. After changing copy, mappings, accents, palette, geometry, or TeX source, regenerate into a new directory and review the new renders; an earlier review does not transfer to changed bytes. These records establish a local screen proof. Browser verification, physical print assessment, typeface selection, and release decisions need their own evidence.
