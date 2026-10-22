# Print-production capability boundary

The current recipe builder produces hash-pinned RGB screen proofs. A two-page slick can declare logical front/back order and a long- or short-edge flip, but the PDF is not imposed for a press and does not carry printer-specific bleed or approval. Keep `physical_print_review: pending` until a separate print handoff exists.

For a customer that needs printed output, collect the printer's trim size, bleed, safe area, duplex convention, imposition responsibility, color space and output profile, black treatment, minimum line weight, raster effective resolution, paper/finish, and proof process. Record the exact approved source and exported PDF hashes. Review a physical proof or printer-approved digital proof at intended size, including front/back alignment, color, small type, and marks near trim.

The print capability can be `not-applicable` for a customer whose work is digital only. A screen review, embedded sRGB intent, or logical duplex declaration cannot advance a print-ready status. The press export and its validation remain future work under MAT-010; this document defines the handoff information and the separate decision boundary.
