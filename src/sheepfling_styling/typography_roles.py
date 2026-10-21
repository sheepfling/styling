"""Bind shared semantic type roles to a family's declared physical faces.

These bindings select font families only. Point sizes, spacing, color, and other
visual treatment belong to the family profile and its composition adapter.
"""
from __future__ import annotations

from collections.abc import Collection, Mapping


SHARED_TYPE_ROLES = (
    "identity.wordmark", "document.kicker", "document.eyebrow", "document.title",
    "document.subtitle", "document.lead", "section.heading", "section.marker",
    "body", "body.strong", "label", "data.numeric", "data.axis", "card.title",
    "caption", "annotation", "footer",
)
PHYSICAL_TYPE_ROLES = {"body", "display", "strong", "wordmark", "mono"}
REQUIRED_PHYSICAL_TYPE_ROLES = frozenset({"body", "display", "strong"})

ROLE_COMMANDS = {
    "identity.wordmark": "TypeIdentityWordmark",
    "document.kicker": "TypeDocumentKicker",
    "document.eyebrow": "TypeDocumentEyebrow",
    "document.title": "TypeDocumentTitle",
    "document.subtitle": "TypeDocumentSubtitle",
    "document.lead": "TypeDocumentLead",
    "section.heading": "TypeSectionHeading",
    "section.marker": "TypeSectionMarker",
    "body": "TypeBody",
    "body.strong": "TypeBodyStrong",
    "label": "TypeLabel",
    "data.numeric": "TypeDataNumeric",
    "data.axis": "TypeDataAxis",
    "card.title": "TypeCardTitle",
    "caption": "TypeCaption",
    "annotation": "TypeAnnotation",
    "footer": "TypeFooter",
}
FACE_COMMANDS = {
    "body": "BodyFace",
    "display": "DisplayFace",
    "strong": "StrongFace",
    "wordmark": "WordmarkFace",
    "mono": "MonoFace",
}


def validate_role_map(
    role_map: Mapping[str, str],
    faces: Mapping[str, object] | Collection[str],
) -> None:
    """Require all 17 roles and bindings to supported, declared face IDs.

    ``faces`` may be a profile's type mapping or a collection of its face IDs.
    Body, display, and strong remain required. Wordmark and mono are optional;
    a family may map any semantic role to one of its other declared faces.
    This function checks bindings, not font files or their provenance.
    """
    if not isinstance(role_map, Mapping):
        raise ValueError("Semantic type role_map must be a mapping")
    if not isinstance(faces, (Mapping, Collection)) or isinstance(faces, (str, bytes)):
        raise ValueError("Physical type faces must be a mapping or collection of face IDs")
    if any(not isinstance(face, str) for face in faces):
        raise ValueError("Physical type face IDs must be strings")
    declared_faces = set(faces)
    missing_faces = REQUIRED_PHYSICAL_TYPE_ROLES - declared_faces
    if missing_faces:
        raise ValueError("Type manifest must define required physical faces: {}".format(
            ", ".join(sorted(missing_faces))))
    unknown_faces = declared_faces - PHYSICAL_TYPE_ROLES
    if unknown_faces:
        raise ValueError("Unsupported physical type face IDs: {}".format(
            ", ".join(sorted(unknown_faces))))

    missing_roles = set(SHARED_TYPE_ROLES) - set(role_map)
    unknown_roles = set(role_map) - set(SHARED_TYPE_ROLES)
    if missing_roles or unknown_roles:
        details = []
        if missing_roles:
            details.append("missing: {}".format(", ".join(sorted(missing_roles))))
        if unknown_roles:
            details.append("unknown: {}".format(", ".join(sorted(map(str, unknown_roles)))))
        raise ValueError("Type manifest must map every shared semantic type role exactly once ({})".format(
            "; ".join(details)))

    for role in SHARED_TYPE_ROLES:
        face = role_map[role]
        if not isinstance(face, str) or face not in PHYSICAL_TYPE_ROLES:
            raise ValueError("Semantic type role '{}' maps to unsupported physical face: {!r}".format(role, face))
        if face not in declared_faces:
            raise ValueError("Semantic type role '{}' maps to undeclared physical face: {}".format(role, face))


def tex_role_definitions(
    role_map: Mapping[str, str],
    faces: Mapping[str, object] | Collection[str],
) -> str:
    """Return safe TeX font selectors in the shared semantic role order.

    The caller defines the physical face commands from its own font files before
    including these definitions. No family font names or fallbacks are embedded.
    """
    validate_role_map(role_map, faces)
    return "".join(
        "\\newcommand{\\" + ROLE_COMMANDS[role] + "}{\\" + FACE_COMMANDS[role_map[role]] + "}\n"
        for role in SHARED_TYPE_ROLES
    )


def css_role_definitions(
    role_map: Mapping[str, str],
    faces: Mapping[str, object] | Collection[str],
) -> str:
    """Bind the same 17 roles to family-owned physical face CSS variables.

    The family defines ``--face-body`` and each other exercised face variable
    from its own local font names and fallbacks. This emits no font files,
    sizes, spacing or palette choices.
    """
    validate_role_map(role_map, faces)
    return "".join(
        '[data-type="' + role + '"] {font-family: var(--face-' + role_map[role] + ');}\n'
        for role in SHARED_TYPE_ROLES
    )
