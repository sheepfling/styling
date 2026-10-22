# Customer intake and portfolio coverage

The [maturation backlog](maturation-backlog.md) tracks platform work. These records track the evidence for one customer's profile without moving private identity files into this public repository. The profile registry continues to use neutral `system-XX` IDs.

## Customer source intake

Start with [the synthetic intake](../examples/starter/customer-intake.json) and the [intake contract](../contracts/customer-intake.json). Put a real customer's intake and its referenced files in an authorized private directory. Every file and rights-evidence record uses a relative path and an exact SHA-256 hash. Typeface bindings refer to declared font source IDs; fonts remain external to the public package.

```sh
python scripts/validate_customer_intake.py examples/starter/customer-intake.json
python scripts/validate_customer_intake.py /path/to/private/system-01.json
```

The validator checks exact source bytes, origins, rights evidence, claim citations, and dependencies between separate route, proof, production, and publication states. `profile_ready` requires an approved route, selected required typefaces, and verified rights for all declared sources. A validated record is evidence of the stated inputs and status dependencies; it does not decide legal rights, verify a marketing claim, or grant publication permission.

Install the optional `preview` dependencies from `pyproject.toml` to validate PDF and browser screenshots (`pypdf` and Pillow).

## Six-profile coverage report

The [coverage evidence contract](../contracts/portfolio-coverage.json) accepts an optional private `system-XX.json` file for each profile. It may contain any subset of the five light-context baseline slots. Missing profiles and slots remain `not-started`. A built slot pins its input and output bytes; a reviewed PDF also pins a [PDF visual-review receipt](../contracts/pdf-review-receipt.json), while a reviewed web output pins a [browser-review receipt](../contracts/web-review-receipt.json). An approved output additionally needs a separate pinned approval record and a validated profile-ready intake. Print evidence is separate and does not change screen-proof status.

```sh
python scripts/report_portfolio_coverage.py --output output/portfolio-coverage.json
python scripts/report_portfolio_coverage.py \
  --intake-dir /path/to/private/intakes \
  --evidence-dir /path/to/private/coverage \
  --output /path/to/private/portfolio-coverage.json
```

The default report lists all six neutral profiles and their 30 required output slots with visible gaps. Supply private directories to include validated customer evidence. The report returns only IDs, states, counts, and hashes; it does not include customer names or source paths. The status of a file is not inferred from another profile's evidence or from a dark-context experiment. Both review receipt formats are validated against current output bytes before a slot advances.

For PDF slots, the receipt must cover every page of the pinned PDF with exact page sizes and pinned PNG previews, plus a reviewer, date, intended use, findings, and limitations. Validate one directly with `python scripts/validate_pdf_review.py /path/to/private/review.json`. For web slots, the receipt must pin the entry, linked sources, screenshots at 320, 390, 768 and 1280 pixels, computed-font and contrast review, and browser details; validate it with `python scripts/validate_web_review.py /path/to/private/browser-review.json`. Both receipts pin a family visual reference and name signature features as preserved, intentionally adapted, or missing, with a concrete observation for each. A missing feature blocks a passed review; the validator checks that the evidence is complete and current, while a human assesses the design judgment. A blocked or stale review cannot advance a slot. Existing local review formats can remain historical evidence; a new coverage claim uses the current receipt format. Automating the browser observations and reviewing actual customer sites remain MAT-005 work.
