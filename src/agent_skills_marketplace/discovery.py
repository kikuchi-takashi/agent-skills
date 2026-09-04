"""Discovery and representation of repository skills."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .frontmatter import FrontmatterError, parse_skill_file


@dataclass
class SkillRecord:
    name: str
    description: str
    path: Path
    collection: str
    fields: Dict[str, Any]

    @property
    def version(self) -> Optional[str]:
        metadata = self.fields.get("metadata", {})
        if isinstance(metadata, dict):
            value = metadata.get("version")
            return str(value) if value is not None else None
        return None

    def to_index_entry(self, root: Path) -> Dict[str, Any]:
        entry: Dict[str, Any] = {
            "id": self.name,
            "name": self.name,
            "description": self.description,
            "collection": self.collection,
            "path": self.path.parent.relative_to(root).as_posix(),
        }
        for key in ("license", "compatibility"):
            if key in self.fields and self.fields[key] != "":
                entry[key] = self.fields[key]
        if self.version is not None:
            entry["version"] = self.version
        return entry


def skill_files(root: Path) -> List[Path]:
    return sorted(root.rglob("SKILL.md"))


def load_skill(path: Path, root: Path) -> SkillRecord:
    fields, _ = parse_skill_file(path)
    relative = path.relative_to(root)
    collection = relative.parts[0] if len(relative.parts) >= 3 else "uncategorized"
    return SkillRecord(
        name=str(fields.get("name", "")),
        description=str(fields.get("description", "")),
        path=path,
        collection=collection,
        fields=fields,
    )
