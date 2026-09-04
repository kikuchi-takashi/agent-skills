"""Marketplace index generation and safe installation."""

from __future__ import annotations

import json
import shutil
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .bundles import BundleRecord, bundle_files, load_bundle
from .discovery import SkillRecord, load_skill, skill_files
from .frontmatter import FrontmatterError, parse_skill_file
from .validation import validate_tree


def discover(root: Path) -> List[SkillRecord]:
    errors = validate_tree(root)
    if errors:
        raise ValueError("\n".join(errors))
    return [load_skill(path, root) for path in skill_files(root)]


def _bundle_skill_names(bundle: BundleRecord) -> List[str]:
    names: List[str] = []
    skill_files_in_bundle = set()
    for relative in bundle.install_paths:
        source = bundle.path.joinpath(*relative.parts)
        if source.name == "SKILL.md":
            skill_files_in_bundle.add(source)
        elif source.is_dir():
            skill_files_in_bundle.update(source.rglob("SKILL.md"))
    for path in sorted(skill_files_in_bundle):
        try:
            fields, _ = parse_skill_file(path)
        except FrontmatterError:
            continue
        names.append(str(fields.get("name", "")))
    return names


def build_index(root: Path, display_name: str) -> Dict[str, Any]:
    errors = validate_tree(root)
    if errors:
        raise ValueError("\n".join(errors))
    records = [load_skill(path, root) for path in skill_files(root)]
    bundles = [load_bundle(path) for path in bundle_files(root)]
    collections: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()
    for record in records:
        collections.setdefault(record.collection, []).append(
            record.to_index_entry(root)
        )

    collection_entries = []
    for name, skills in collections.items():
        collection_entries.append(
            {
                "id": name,
                "name": name.upper() if name in ("pdf", "pptx") else name,
                "skills": [skill["id"] for skill in skills],
            }
        )

    for bundle in bundles:
        collection_entries.append(
            {
                "id": bundle.id,
                "name": bundle.name,
                "kind": "bundle",
                "skills": _bundle_skill_names(bundle),
                "bundles": [bundle.id],
            }
        )

    return {
        "schemaVersion": "0.2",
        "name": display_name,
        "collections": collection_entries,
        "skills": [record.to_index_entry(root) for record in records],
        "bundles": [
            bundle.to_index_entry(root, _bundle_skill_names(bundle))
            for bundle in bundles
        ],
    }


def write_index(root: Path, output: Path, display_name: str) -> None:
    index = build_index(root, display_name)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _ensure_target_outside_root(root: Path, target: Path) -> None:
    resolved_root = root.resolve()
    resolved_target = target.resolve()
    if resolved_target == resolved_root or resolved_root in resolved_target.parents:
        raise ValueError(
            "install target must be outside the collection root: {0}".format(target)
        )


def _bundle_entries(
    bundle: BundleRecord, target: Path
) -> Tuple[List[Path], List[Tuple[Path, Path]]]:
    directories: List[Path] = []
    files: List[Tuple[Path, Path]] = []
    for relative in bundle.install_paths:
        source = bundle.path.joinpath(*relative.parts)
        destination = target.joinpath(*relative.parts)
        if source.is_dir():
            directories.append(destination)
            for candidate in sorted(source.rglob("*")):
                child = candidate.relative_to(bundle.path)
                child_destination = target / child
                if candidate.is_dir():
                    directories.append(child_destination)
                else:
                    files.append((candidate, child_destination))
        else:
            files.append((source, destination))
    return directories, files


def _install_bundle(
    bundle: BundleRecord, root: Path, target: Path, force: bool
) -> List[Path]:
    _ensure_target_outside_root(root, target)
    if target.is_symlink():
        raise ValueError(
            "bundle install target must not be a symlink: {0}".format(target)
        )

    directories, files = _bundle_entries(bundle, target)
    for directory in directories:
        if directory.is_symlink():
            raise ValueError(
                "bundle destination contains a symlink: {0}".format(directory)
            )
        if directory.exists() and not directory.is_dir():
            raise FileExistsError(
                "bundle directory conflicts with file: {0}".format(directory)
            )
    for _, destination in files:
        current = destination.parent
        while current != target.parent:
            if current.is_symlink():
                raise ValueError(
                    "bundle destination contains a symlink: {0}".format(current)
                )
            if current == target:
                break
            current = current.parent
        if destination.is_symlink():
            raise ValueError(
                "bundle destination contains a symlink: {0}".format(destination)
            )
        if destination.exists():
            if not destination.is_file():
                raise FileExistsError(
                    "bundle file conflicts with directory: {0}".format(destination)
                )
            if not force:
                raise FileExistsError(
                    "destination exists: {0}; use --force to replace it".format(
                        destination
                    )
                )

    target.mkdir(parents=True, exist_ok=True)
    for directory in sorted(set(directories), key=lambda value: len(value.parts)):
        directory.mkdir(parents=True, exist_ok=True)
    for source, destination in files:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(source), str(destination))
    return [target.joinpath(*path.parts) for path in bundle.install_paths]


def install(query: str, root: Path, target: Path, force: bool = False) -> List[Path]:
    records = discover(root)
    bundles = [load_bundle(path) for path in bundle_files(root)]
    if query.startswith("bundle:"):
        bundle_id = query.split(":", 1)[1]
        selected_bundles = [bundle for bundle in bundles if bundle.id == bundle_id]
        if not selected_bundles:
            raise ValueError("bundle not found: {0}".format(bundle_id))
        return _install_bundle(selected_bundles[0], root, target, force)
    if query.startswith("collection:"):
        collection = query.split(":", 1)[1]
        if any(bundle.id == collection for bundle in bundles):
            raise ValueError(
                "collection '{0}' is a bundle; use bundle:{0}".format(collection)
            )
        selected = [record for record in records if record.collection == collection]
        if not selected:
            raise ValueError("collection not found: {0}".format(collection))
    else:
        selected = [record for record in records if record.name == query]
        if not selected:
            raise ValueError("skill not found: {0}".format(query))

    _ensure_target_outside_root(root, target)

    destinations = [(record, target / record.name) for record in selected]
    for record, destination in destinations:
        source = record.path.parent.resolve()
        resolved_destination = destination.resolve()
        if (
            resolved_destination == source
            or source in resolved_destination.parents
            or resolved_destination in source.parents
        ):
            raise ValueError(
                "install destination overlaps source: {0}".format(destination)
            )

    if not force:
        existing = [
            destination for _, destination in destinations if destination.exists()
        ]
        if existing:
            raise FileExistsError(
                "destination exists: {0}; use --force to replace it".format(existing[0])
            )

    target.mkdir(parents=True, exist_ok=True)
    installed: List[Path] = []
    for record, destination in destinations:
        if destination.exists():
            shutil.rmtree(str(destination))
        shutil.copytree(str(record.path.parent), str(destination))
        installed.append(destination)
    return installed
