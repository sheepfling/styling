"""Resolve brand-owned asset packs without coupling a renderer to one brand."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
INTERFACE_VERSION = "0.1.0"


class AssetPackError(ValueError):
    """An asset pack is malformed, unavailable, or inconsistent with its pins."""


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssetPackError("Cannot read asset-pack JSON: {}".format(path)) from exc
    if not isinstance(value, dict):
        raise AssetPackError("Asset-pack JSON must be an object: {}".format(path))
    return value


def _repo_file(root: Path, relative: str, label: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise AssetPackError("{} must be a repository-relative path".format(label))
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise AssetPackError("{} escapes the repository".format(label))
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_asset_pack(
    repo_root: Path,
    contract_path: str | Path,
    pack_id: str,
) -> Dict[str, Any]:
    """Resolve one exact pack id and verify available bytes without importing refs.

    ``source_reference_only`` assets are returned as metadata only. The loader
    never guesses a local path for an unavailable source asset.
    """
    root = Path(repo_root).resolve()
    contract_file = Path(contract_path)
    if not contract_file.is_absolute():
        contract_file = root / contract_file
    contract_file = contract_file.resolve()
    if not contract_file.is_relative_to(root):
        raise AssetPackError("Asset-pack contract must stay inside the repository")
    contract = _read_json(contract_file)
    if contract.get("interface_id") != "brand-asset-pack" or contract.get("interface_version") != INTERFACE_VERSION:
        raise AssetPackError("Unsupported asset-pack interface identity or version")

    packs = contract.get("packs")
    if not isinstance(packs, list):
        raise AssetPackError("Asset-pack contract must contain a packs list")
    matches = [item for item in packs if isinstance(item, dict) and item.get("pack_id") == pack_id]
    if len(matches) != 1:
        raise AssetPackError("Asset pack id must resolve to exactly one record: {}".format(pack_id))
    pack = matches[0]
    if not pack.get("brand") or pack.get("profile_version") != "0.1.0":
        raise AssetPackError("Asset packs must identify their brand and 0.1.0 profile")
    if pack.get("availability") not in ("local_assets_present", "source_reference_only"):
        raise AssetPackError("Unsupported asset-pack availability state")

    source_record_path = _repo_file(root, pack.get("source_record"), "source_record")
    if not source_record_path.is_file():
        raise AssetPackError("Missing asset-pack source record: {}".format(pack.get("source_record")))
    source_record_sha256 = pack.get("source_record_sha256")
    if source_record_sha256 is not None:
        if not isinstance(source_record_sha256, str) or not SHA256_PATTERN.fullmatch(source_record_sha256):
            raise AssetPackError("source_record_sha256 must be lowercase SHA-256")
        if _sha256(source_record_path) != source_record_sha256:
            raise AssetPackError("Asset-pack source record digest mismatch: {}".format(pack_id))

    assets = pack.get("assets")
    if not isinstance(assets, list) or not assets:
        raise AssetPackError("Asset packs must declare at least one asset record")
    resolved_assets = []
    local_asset_count = 0
    font_roles = {"display-font", "body-font", "supporting-font"}
    for asset in assets:
        if not isinstance(asset, dict):
            raise AssetPackError("Each asset record must be an object")
        for field in ("asset_id", "role", "sha256", "source_path", "provenance", "rights_note"):
            if not asset.get(field):
                raise AssetPackError("Asset record is missing {}".format(field))
        digest = asset["sha256"]
        if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
            raise AssetPackError("Asset SHA-256 must be lowercase SHA-256")
        state = asset.get("availability")
        resolved = dict(asset)
        if state == "available_local":
            local_path = _repo_file(root, asset.get("path"), "asset path")
            if not local_path.is_file():
                raise AssetPackError("Missing local asset: {}".format(asset.get("path")))
            actual = _sha256(local_path)
            if actual != digest:
                raise AssetPackError("Asset digest mismatch: {}".format(asset["asset_id"]))
            resolved["resolved_local"] = True
            license_record = asset.get("license")
            if asset["role"] in font_roles and not isinstance(license_record, dict):
                raise AssetPackError("Local font asset requires a pinned license: {}".format(asset["asset_id"]))
            if license_record is not None:
                if not isinstance(license_record, dict):
                    raise AssetPackError("Asset license must be an object: {}".format(asset["asset_id"]))
                for field in ("name", "path", "sha256"):
                    if not license_record.get(field):
                        raise AssetPackError("Asset license is missing {}: {}".format(field, asset["asset_id"]))
                license_digest = license_record["sha256"]
                if not isinstance(license_digest, str) or not SHA256_PATTERN.fullmatch(license_digest):
                    raise AssetPackError("License SHA-256 must be lowercase SHA-256: {}".format(asset["asset_id"]))
                license_path = _repo_file(root, license_record["path"], "license path")
                if not license_path.is_file():
                    raise AssetPackError("Missing local license: {}".format(license_record["path"]))
                if _sha256(license_path) != license_digest:
                    raise AssetPackError("License digest mismatch: {}".format(asset["asset_id"]))
                resolved["license"] = dict(license_record)
                resolved["license"]["verified_local"] = True
            local_asset_count += 1
        elif state == "source_reference_only":
            if asset.get("path") is not None:
                raise AssetPackError("Reference-only asset must not claim a local path")
            resolved["resolved_local"] = False
        else:
            raise AssetPackError("Unsupported asset availability for {}".format(asset["asset_id"]))
        resolved_assets.append(resolved)

    if pack["availability"] == "local_assets_present" and local_asset_count == 0:
        raise AssetPackError("Pack claims local assets but none resolve locally")
    if pack["availability"] == "source_reference_only" and local_asset_count:
        raise AssetPackError("Reference-only pack must not claim local asset bytes")

    return {
        "pack_id": pack_id,
        "brand": pack["brand"],
        "profile_version": pack["profile_version"],
        "availability": pack["availability"],
        "source_record": pack["source_record"],
        "source_record_sha256": source_record_sha256,
        "assets": resolved_assets,
    }


def validate_all_asset_packs(repo_root: Path, contract_path: str | Path) -> Dict[str, Dict[str, Any]]:
    root = Path(repo_root).resolve()
    path = Path(contract_path)
    if not path.is_absolute():
        path = root / path
    contract = _read_json(path)
    packs = contract.get("packs")
    if not isinstance(packs, list):
        raise AssetPackError("Asset-pack contract must contain a packs list")
    ids = [item.get("pack_id") for item in packs if isinstance(item, dict)]
    if len(ids) != len(packs) or len(set(ids)) != len(ids):
        raise AssetPackError("Asset-pack ids must be unique")
    return {pack_id: load_asset_pack(root, path, pack_id) for pack_id in ids}
