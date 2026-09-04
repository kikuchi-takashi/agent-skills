"""Bundle manifests for collections that must be installed as one tree."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List


BUNDLE_FILE = "bundle.json"


class BundleError(ValueError):
    """Raised when a bundle manifest cannot be read."""


@dataclass
class BundleRecord:
    id: str
    name: str
    description: str
    path: Path
    fields: Dict[str, Any]
    install_paths: List[PurePosixPath]

    def to_index_entry(self, root: Path, skill_names: List[str]) -> Dict[str, Any]:
        entry: Dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "collection": self.id,
            "path": self.path.relative_to(root).as_posix(),
            "install": {
                "mode": "overlay",
                "paths": [path.as_posix() for path in self.install_paths],
            },
            "skills": skill_names,
        }
        for key in ("license", "compatibility", "version"):
            if key in self.fields and self.fields[key] != "":
                entry[key] = self.fields[key]
        return entry


def bundle_files(root: Path) -> List[Path]:
    return sorted(path for path in root.glob("*/{0}".format(BUNDLE_FILE)))


def load_bundle(path: Path) -> BundleRecord:
    try:
        fields = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BundleError(str(exc))
    if not isinstance(fields, dict):
        raise BundleError("bundle manifest must be a JSON object")

    install = fields.get("install", {})
    raw_paths = install.get("paths", []) if isinstance(install, dict) else []
    install_paths = [PurePosixPath(value) for value in raw_paths if isinstance(value, str)]
    return BundleRecord(
        id=str(fields.get("id", "")),
        name=str(fields.get("name", "")),
        description=str(fields.get("description", "")),
        path=path.parent,
        fields=fields,
        install_paths=install_paths,
    )
