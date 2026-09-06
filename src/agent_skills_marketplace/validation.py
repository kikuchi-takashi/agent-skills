"""Validation against the portable Agent Skills metadata contract."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

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


def validate_skill(path: Path, root: Path) -> List[str]:
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


def validate_tree(root: Path) -> List[str]:
    if not root.exists():
        return ["root does not exist: {0}".format(root)]
    if not root.is_dir():
        return ["root is not a directory: {0}".format(root)]

    errors: List[str] = []
    files = skill_files(root)
    for path in files:
        errors.extend(validate_skill(path, root))

    # Names are repository-wide identifiers.
    seen: Dict[str, Path] = {}
    bundles: Dict[str, List[Path]] = {}
    bundle_collections: Dict[str, set] = {}
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

        metadata = record.fields.get("metadata", {})
        bundle = metadata.get("bundle") if isinstance(metadata, dict) else None
        if bundle is not None:
            if (
                not isinstance(bundle, str)
                or len(bundle) > 64
                or not NAME_PATTERN.match(bundle)
            ):
                errors.append(
                    "{0}: metadata.bundle must be lowercase kebab-case and "
                    "1-64 characters".format(path)
                )
                continue
            bundles.setdefault(bundle, []).append(path)
            bundle_collections.setdefault(bundle, set()).add(record.collection)

    for bundle, paths in sorted(bundles.items()):
        if len(paths) < 2:
            errors.append(
                "bundle '{0}' must contain at least two skills: {1}".format(
                    bundle, paths[0]
                )
            )
        if len(bundle_collections[bundle]) != 1:
            errors.append(
                "bundle '{0}' must stay within one collection: {1}".format(
                    bundle, ", ".join(sorted(bundle_collections[bundle]))
                )
            )

    if not files:
        errors.append("no SKILL.md files found under {0}".format(root))
    return errors
