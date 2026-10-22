# Route-aware family system assembly

A customer family can own several composition packages and several visual routes. The [assembly contract](../contracts/family-system-assembly.json) connects their pinned proof reports without moving typography or layout into a common template. One family-level audit shows which outputs are baseline candidates, which remain experiments, and which signature features need visual review on each output.

The assembly manifest stays with private evidence. It names an overarching `family_id`; each build also names the exact `source_family_id` from its own build report. This explicit link accommodates separately authored document and product packages without guessing their identity from filenames. A build declares `native-tex`, `native-vector`, or `composition-recipe`. Native reports carry their own route; a recipe build supplies a route in the assembly manifest. Route states are `selected-for-now` or `proposed-unselected`. They express a working design decision, not customer approval.

```json
{
  "schema_version": "0.1.0",
  "family_id": "sample-system",
  "routes": [{
    "id": "editorial",
    "state": "selected-for-now",
    "signature_features": [{
      "id": "open-reading-rhythm",
      "description": "The family-owned title and body retain generous, uneven spacing.",
      "outputs": ["one-page", "two-page"]
    }]
  }],
  "builds": [{
    "kind": "composition-recipe",
    "route": "editorial",
    "source_family_id": "sample-document-package",
    "report": {"path": "sample-build/build-report.json", "sha256": "<exact lowercase SHA-256>"}
  }]
}
```

Place the manifest in a private directory that also contains the build directories, then run:

```sh
python3 scripts/audit_family_system.py /path/to/private/family-system.json \
  --output /path/to/private/family-system-audit.json
```

The audit rechecks the report pin, current PDF and preview bytes, page counts, native input manifest and staged source pins, and visual-representation metadata. It rejects undeclared routes, duplicate `route/output` identities, absent signature features, changed proof bytes, and baseline claims from unselected routes. Its output keys include the route (`editorial/one-page`), so three product slicks can share a slot without one silently replacing the others. A mixed- or dark-context slick remains visible in the route matrix but does not fill a light baseline slot. Historical native web source remains `source-only`; a recipe web proof requires its own static and browser review.

The signature list is a **review checklist**. The audit confirms every built output has at least one declared feature, but does not decide whether that feature survived visually. A current family-character review receipt must compare actual-size proofs to a separate reference before a slot advances. Customer source rights, claims, physical print, publication, and approval remain separate gates. The family-level audit is not a substitute for the six neutral profile coverage records.

For connected front/back product suites, the [product-story audit](product-story-system.md) binds identities, duplex faces, replaceable image stages, concept facets and handoffs to these exact route/output proofs. The family assembly itself keeps all PDF and web formats available without requiring every family to use that product grammar.

Private local packets exercise several assembly shapes: a selected native TeX route, multiple proposed native SVG routes, and a selected document route connected to distinct product routes. Unselected and non-light proofs remain visible experiments without filling light baseline slots. These exact-byte studies validate source and output relationships; they do not imply that newer sources or customer approvals have been reconciled.
