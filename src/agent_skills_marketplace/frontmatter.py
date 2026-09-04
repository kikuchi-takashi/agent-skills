"""Small dependency-free parser for the scalar frontmatter used by SKILL.md."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple


class FrontmatterError(ValueError):
    """Raised when a SKILL.md frontmatter block cannot be read."""


def _scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        content = value[1:-1].strip()
        if not content:
            return []
        return [_scalar(item) for item in content.split(",")]
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    return value


def parse_skill_file(path: Path) -> Tuple[Dict[str, Any], str]:
    """Return ``(frontmatter, markdown_body)`` for a skill file.

    The implementation intentionally supports the small subset needed for
    Agent Skills metadata while avoiding a runtime dependency on a YAML
    package. Nested mappings are supported for ``metadata``.
    """

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FrontmatterError(str(exc))

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise FrontmatterError("SKILL.md must start with YAML frontmatter")

    closing = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            closing = index
            break
    if closing is None:
        raise FrontmatterError("frontmatter closing delimiter '---' is missing")

    fields: Dict[str, Any] = {}
    current_mapping: Dict[str, Any] = fields
    current_key = None

    for line_number, line in enumerate(lines[1:closing], start=2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue

        indentation = len(line) - len(line.lstrip(" "))
        if indentation and current_key == "metadata":
            if ":" not in line:
                raise FrontmatterError(
                    "invalid metadata entry on line {0}".format(line_number)
                )
            key, value = line.strip().split(":", 1)
            metadata = fields.setdefault("metadata", {})
            if not isinstance(metadata, dict):
                raise FrontmatterError("metadata must be a mapping")
            metadata[key.strip()] = _scalar(value)
            continue

        if indentation:
            raise FrontmatterError(
                "unexpected indentation on line {0}".format(line_number)
            )
        if ":" not in line:
            raise FrontmatterError(
                "invalid frontmatter entry on line {0}".format(line_number)
            )
        key, value = line.split(":", 1)
        key = key.strip()
        if not key:
            raise FrontmatterError(
                "frontmatter key is empty on line {0}".format(line_number)
            )
        parsed_value = _scalar(value)
        fields[key] = {} if key == "metadata" and parsed_value == "" else parsed_value
        current_key = key

    body = "\n".join(lines[closing + 1 :])
    return fields, body
