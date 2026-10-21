"""Semantic PDF typography must follow a family's role bindings."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sheepfling_styling.typography_roles import (
    PHYSICAL_TYPE_ROLES,
    ROLE_COMMANDS,
    SHARED_TYPE_ROLES,
    css_role_definitions,
    tex_role_definitions,
    validate_role_map,
)


def role_map():
    return {
        role: "body" if role in {"body", "document.lead", "caption", "annotation", "footer"}
        else "wordmark" if role == "identity.wordmark"
        else "strong" if role == "body.strong"
        else "display"
        for role in SHARED_TYPE_ROLES
    }


class TypographyRoleTests(unittest.TestCase):
    def test_role_vocabulary_matches_versioned_suite_contract(self):
        contract = json.loads((ROOT / "contracts/typography-deliverable-suite.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["suite_version"], "0.5.0")
        self.assertEqual(list(SHARED_TYPE_ROLES), contract["shared_typography_roles"])
        self.assertEqual(PHYSICAL_TYPE_ROLES, set(contract["typography_role_policy"]["physical_face_ids"]))
        self.assertEqual(set(ROLE_COMMANDS), set(SHARED_TYPE_ROLES))
        self.assertEqual(len(set(ROLE_COMMANDS.values())), 17)

    def test_legacy_four_faces_preserve_exact_font_selectors(self):
        faces = {name: {} for name in ("body", "display", "strong", "wordmark")}
        source = tex_role_definitions(role_map(), faces)
        self.assertEqual(source.count(r"\newcommand{"), 17)
        self.assertIn(r"\newcommand{\TypeIdentityWordmark}{\WordmarkFace}", source)
        self.assertIn(r"\newcommand{\TypeDocumentTitle}{\DisplayFace}", source)
        self.assertIn(r"\newcommand{\TypeBody}{\BodyFace}", source)
        self.assertIn(r"\newcommand{\TypeBodyStrong}{\StrongFace}", source)
        self.assertNotIn(r"\MonoFace", source)
        self.assertTrue(source.endswith("\n"))

    def test_permuting_every_binding_changes_the_emitted_font_selector(self):
        faces = ("body", "display", "strong", "wordmark", "mono")
        original = {role: faces[index % len(faces)] for index, role in enumerate(SHARED_TYPE_ROLES)}
        changed = {role: faces[(index + 1) % len(faces)] for index, role in enumerate(SHARED_TYPE_ROLES)}
        source = tex_role_definitions(original, faces)
        remapped = tex_role_definitions(changed, faces)
        selectors = {"body": "BodyFace", "display": "DisplayFace", "strong": "StrongFace", "wordmark": "WordmarkFace", "mono": "MonoFace"}
        for role, command in ROLE_COMMANDS.items():
            with self.subTest(role=role):
                before = "\\newcommand{\\" + command + "}{\\" + selectors[original[role]] + "}"
                after = "\\newcommand{\\" + command + "}{\\" + selectors[changed[role]] + "}"
                self.assertIn(before, source)
                self.assertIn(after, remapped)
                self.assertNotIn(before, remapped)

    def test_wordmark_and_mono_are_optional_declared_faces(self):
        bindings = role_map()
        bindings["identity.wordmark"] = "display"
        validate_role_map(bindings, {"body", "display", "strong"})
        bindings["label"] = "mono"
        with self.assertRaisesRegex(ValueError, "undeclared physical face: mono"):
            validate_role_map(bindings, {"body", "display", "strong"})
        source = tex_role_definitions(bindings, {"body", "display", "strong", "mono"})
        self.assertIn(r"\newcommand{\TypeLabel}{\MonoFace}", source)

    def test_web_and_pdf_selectors_follow_the_same_role_remapping_without_font_defaults(self):
        bindings = role_map()
        before = css_role_definitions(bindings, PHYSICAL_TYPE_ROLES)
        bindings["document.title"] = "mono"
        after = css_role_definitions(bindings, PHYSICAL_TYPE_ROLES)
        self.assertIn('[data-type="document.title"] {font-family: var(--face-display);}', before)
        self.assertIn('[data-type="document.title"] {font-family: var(--face-mono);}', after)
        self.assertNotIn('[data-type="document.title"] {font-family: var(--face-display);}', after)
        self.assertIn(r"\newcommand{\TypeDocumentTitle}{\MonoFace}", tex_role_definitions(bindings, PHYSICAL_TYPE_ROLES))
        self.assertEqual(after.count('[data-type="'), 17)
        self.assertNotIn("@font-face", after)
        self.assertNotIn("font-size", after)
        with self.assertRaisesRegex(ValueError, "undeclared physical face: mono"):
            css_role_definitions(bindings, {"body", "display", "strong", "wordmark"})

    def test_all_roles_are_required_and_unknown_roles_are_rejected(self):
        bindings = role_map()
        del bindings["caption"]
        bindings["unknown.role"] = "body"
        with self.assertRaisesRegex(ValueError, "missing: caption; unknown: unknown.role"):
            validate_role_map(bindings, PHYSICAL_TYPE_ROLES)

    def test_unknown_and_invalid_bindings_are_rejected_before_tex_generation(self):
        for value in ("heading", r"body}\input{other}", None, ["body"]):
            bindings = role_map()
            bindings["document.title"] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "document.title.*unsupported physical face"):
                tex_role_definitions(bindings, PHYSICAL_TYPE_ROLES)

    def test_required_and_supported_physical_faces_are_enforced(self):
        with self.assertRaisesRegex(ValueError, "required physical faces: strong"):
            validate_role_map(role_map(), {"body", "display", "wordmark"})
        with self.assertRaisesRegex(ValueError, "Unsupported physical type face IDs: headline"):
            validate_role_map(role_map(), PHYSICAL_TYPE_ROLES | {"headline"})

    def test_invalid_container_inputs_raise_value_error(self):
        with self.assertRaisesRegex(ValueError, "role_map must be a mapping"):
            validate_role_map(None, PHYSICAL_TYPE_ROLES)
        for faces in (None, "body", ["body", "display", "strong", 1]):
            with self.subTest(faces=faces), self.assertRaises(ValueError):
                validate_role_map(role_map(), faces)


if __name__ == "__main__":
    unittest.main()
