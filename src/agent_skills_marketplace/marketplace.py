"""Marketplace index generation and safe installation."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List

from .discovery import SkillRecord, load_skill, skill_files
from .validation import validate_tree


def discover(root: Path) -> List[SkillRecord]:
    errors = validate_tree(root)
    if errors:
        raise ValueError("\n".join(errors))
    return [load_skill(path, root) for path in skill_files(root)]


def build_index(root: Path, display_name: str) -> Dict[str, Any]:
    records = discover(root)
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

    return {
        "schemaVersion": "0.1",
        "name": display_name,
        "collections": collection_entries,
        "skills": [record.to_index_entry(root) for record in records],
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


def _remove_installed_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(str(path))


def _path_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def install(query: str, root: Path, target: Path, force: bool = False) -> List[Path]:
    records = discover(root)
    if query.startswith("collection:"):
        collection = query.split(":", 1)[1]
        selected = [record for record in records if record.collection == collection]
        if not selected:
            raise ValueError("collection not found: {0}".format(collection))
    else:
        selected = [record for record in records if record.name == query]
        if not selected:
            raise ValueError("skill not found: {0}".format(query))
        bundle = selected[0].bundle
        if bundle:
            selected = [record for record in records if record.bundle == bundle]

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
            destination for _, destination in destinations if _path_exists(destination)
        ]
        if existing:
            raise FileExistsError(
                "destination exists: {0}; use --force to replace it".format(existing[0])
            )

    if target.exists() and not target.is_dir():
        raise NotADirectoryError("install target is not a directory: {0}".format(target))

    target_existed = target.exists()
    target.mkdir(parents=True, exist_ok=True)
    transaction = None
    preserve_transaction = False
    try:
        transaction = Path(
            tempfile.mkdtemp(prefix=".skills-install-", dir=str(target))
        )
        staged_root = transaction / "staged"
        backup_root = transaction / "backup"
        staged_root.mkdir()
        backup_root.mkdir()

        # Complete every potentially failing copy before changing destinations.
        for record, _ in destinations:
            shutil.copytree(str(record.path.parent), str(staged_root / record.name))

        # Close the gap between the initial preflight and the commit phase.
        if not force:
            existing = [
                destination
                for _, destination in destinations
                if _path_exists(destination)
            ]
            if existing:
                raise FileExistsError(
                    "destination exists: {0}; use --force to replace it".format(
                        existing[0]
                    )
                )

        backups: List[tuple[Path, Path]] = []
        installed: List[Path] = []
        try:
            if force:
                for record, destination in destinations:
                    if _path_exists(destination):
                        backup = backup_root / record.name
                        os.replace(str(destination), str(backup))
                        backups.append((backup, destination))

            for record, destination in destinations:
                staged = staged_root / record.name
                os.replace(str(staged), str(destination))
                installed.append(destination)
        except OSError as install_error:
            rollback_errors = []
            for destination in reversed(installed):
                try:
                    _remove_installed_path(destination)
                except OSError as exc:
                    rollback_errors.append(str(exc))
            for backup, destination in reversed(backups):
                try:
                    os.replace(str(backup), str(destination))
                except OSError as exc:
                    rollback_errors.append(str(exc))
            if rollback_errors:
                preserve_transaction = True
                raise OSError(
                    "install failed: {0}; rollback failed: {1}; "
                    "recovery data retained at {2}".format(
                        install_error, "; ".join(rollback_errors), transaction
                    )
                ) from install_error
            raise

        return installed
    except Exception:
        if not target_existed:
            try:
                target.rmdir()
            except OSError:
                pass
        raise
    finally:
        if transaction is not None and not preserve_transaction:
            shutil.rmtree(str(transaction), ignore_errors=True)
