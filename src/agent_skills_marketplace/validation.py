"""Validation against the portable Agent Skills metadata contract."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Dict, List

from .bundles import BundleError, bundle_files, load_bundle
from .discovery import load_skill, skill_files
from .frontmatter import FrontmatterError


ALLOWED_FIELDS = {
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
}
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
BUNDLE_FIELDS = {
    "schemaVersion",
    "id",
    "name",
    "description",
    "license",
    "compatibility",
    "version",
    "install",
}


def validate_skill(path: Path, root: Path, enforce_layout: bool = True) -> List[str]:
    errors: List[str] = []
    try:
        record = load_skill(path, root)
    except (FrontmatterError, ValueError) as exc:
        return ["{0}: {1}".format(path, exc)]

    unknown = sorted(set(record.fields) - ALLOWED_FIELDS)
    if unknown:
        errors.append(
            "{0}: unsupported frontmatter field(s): {1}".format(
                path, ", ".join(unknown)
            )
        )

    if enforce_layout:
        relative = path.relative_to(root)
        if len(relative.parts) != 3:
            errors.append(
                "{0}: skill must be located at "
                "<root>/<collection>/<skill-name>/SKILL.md".format(path)
            )
        else:
            collection = relative.parts[0]
            if len(collection) > 64 or not NAME_PATTERN.match(collection):
                errors.append(
                    "{0}: collection must be lowercase kebab-case and "
                    "1-64 characters".format(path)
                )

    if not record.name:
        errors.append("{0}: name is required".format(path))
    elif len(record.name) > 64 or not NAME_PATTERN.match(record.name):
        errors.append(
            "{0}: name must be lowercase kebab-case and 1-64 characters".format(path)
        )
    elif record.name != path.parent.name:
        errors.append(
            "{0}: name '{1}' must match directory '{2}'".format(
                path, record.name, path.parent.name
            )
        )

    if not record.description:
        errors.append("{0}: description is required".format(path))
    elif len(record.description) > 1024:
        errors.append("{0}: description must be at most 1024 characters".format(path))
    elif "<" in record.description or ">" in record.description:
        errors.append("{0}: description must not contain angle brackets".format(path))

    compatibility = record.fields.get("compatibility")
    if compatibility is not None and len(str(compatibility)) > 500:
        errors.append("{0}: compatibility must be at most 500 characters".format(path))

    metadata = record.fields.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        errors.append("{0}: metadata must be a mapping".format(path))

    for candidate in path.parent.rglob("*"):
        if candidate.is_symlink():
            errors.append(
                "{0}: symlinks are not allowed in portable skill packages: {1}".format(
                    path, candidate
                )
            )

    return errors


def validate_bundle(path: Path, root: Path) -> List[str]:
    errors: List[str] = []
    try:
        bundle = load_bundle(path)
    except BundleError as exc:
        return ["{0}: {1}".format(path, exc)]

    unknown = sorted(set(bundle.fields) - BUNDLE_FIELDS)
    if unknown:
        errors.append(
            "{0}: unsupported bundle field(s): {1}".format(path, ", ".join(unknown))
        )

    if bundle.fields.get("schemaVersion") != "0.1":
        errors.append("{0}: schemaVersion must be '0.1'".format(path))
    raw_id = bundle.fields.get("id")
    if (
        not isinstance(raw_id, str)
        or not bundle.id
        or len(bundle.id) > 64
        or not NAME_PATTERN.match(bundle.id)
    ):
        errors.append("{0}: id must be lowercase kebab-case".format(path))
    elif bundle.id != path.parent.name:
        errors.append("{0}: id must match collection directory".format(path))
    if not isinstance(bundle.fields.get("name"), str) or not bundle.name:
        errors.append("{0}: name is required".format(path))
    if not isinstance(bundle.fields.get("description"), str) or not bundle.description:
        errors.append("{0}: description is required".format(path))
    elif len(bundle.description) > 1024:
        errors.append("{0}: description must be at most 1024 characters".format(path))
    elif "<" in bundle.description or ">" in bundle.description:
        errors.append("{0}: description must not contain angle brackets".format(path))
    version = bundle.fields.get("version")
    if version is not None and (not isinstance(version, str) or not version):
        errors.append("{0}: version must be a non-empty string".format(path))
    license_name = bundle.fields.get("license")
    if not isinstance(license_name, str) or not license_name:
        errors.append("{0}: license is required".format(path))
    compatibility = bundle.fields.get("compatibility")
    if compatibility is not None and (
        not isinstance(compatibility, str) or len(compatibility) > 500
    ):
        errors.append(
            "{0}: compatibility must be a string of at most 500 characters".format(
                path
            )
        )

    install = bundle.fields.get("install")
    if not isinstance(install, dict):
        errors.append("{0}: install must be an object".format(path))
        return errors
    unknown_install = sorted(set(install) - {"mode", "paths"})
    if unknown_install:
        errors.append(
            "{0}: unsupported install field(s): {1}".format(
                path, ", ".join(unknown_install)
            )
        )
    if install.get("mode") != "overlay":
        errors.append("{0}: install.mode must be 'overlay'".format(path))
    raw_paths = install.get("paths")
    if not isinstance(raw_paths, list) or not raw_paths:
        errors.append("{0}: install.paths must be a non-empty list".format(path))
        return errors
    if len(bundle.install_paths) != len(raw_paths):
        errors.append("{0}: every install path must be a string".format(path))
        return errors
    if PurePosixPath("LICENSE") not in bundle.install_paths:
        errors.append("{0}: install.paths must include LICENSE".format(path))

    seen = set()
    for relative in bundle.install_paths:
        if (
            relative.is_absolute()
            or not relative.parts
            or ".." in relative.parts
            or relative == PurePosixPath(".")
        ):
            errors.append("{0}: unsafe install path: {1}".format(path, relative))
            continue
        if relative in seen:
            errors.append("{0}: duplicate install path: {1}".format(path, relative))
        seen.add(relative)
        source = bundle.path.joinpath(*relative.parts)
        if not source.exists():
            errors.append("{0}: install path does not exist: {1}".format(path, relative))
            continue
        candidates = [source]
        if source.is_dir():
            candidates.extend(source.rglob("*"))
        for candidate in candidates:
            if candidate.is_symlink():
                errors.append(
                    "{0}: symlinks are not allowed in bundles: {1}".format(
                        path, candidate
                    )
                )

    ordered = sorted(seen, key=lambda value: len(value.parts))
    for index, parent in enumerate(ordered):
        for child in ordered[index + 1 :]:
            if parent in child.parents:
                errors.append(
                    "{0}: overlapping install paths: {1} and {2}".format(
                        path, parent, child
                    )
                )
    return errors


def validate_tree(root: Path) -> List[str]:
    if not root.exists():
        return ["root does not exist: {0}".format(root)]
    if not root.is_dir():
        return ["root is not a directory: {0}".format(root)]

    errors: List[str] = []
    distributable = set(skill_files(root))
    for path in distributable:
        errors.extend(validate_skill(path, root))

    bundles = bundle_files(root)
    for path in bundles:
        errors.extend(validate_bundle(path, root))

    bundle_roots = {path.parent for path in bundles}
    for path in sorted(root.rglob("SKILL.md")):
        if path in distributable:
            continue
        if any(bundle_root in path.parents for bundle_root in bundle_roots):
            errors.extend(validate_skill(path, root, enforce_layout=False))

    # Names remain repository-wide identifiers inside bundles as well.
    seen: Dict[str, Path] = {}
    for path in sorted(root.rglob("SKILL.md")):
        try:
            record = load_skill(path, root)
        except (FrontmatterError, ValueError):
            continue
        if record.name in seen:
            errors.append(
                "duplicate skill name '{0}': {1} and {2}".format(
                    record.name, seen[record.name], path
                )
            )
        else:
            seen[record.name] = path

    if not distributable and not bundles:
        errors.append("no skills or bundles found under {0}".format(root))
    return errors
