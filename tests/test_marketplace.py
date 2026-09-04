import json
import tempfile
import unittest
from pathlib import Path

from agent_skills_marketplace.marketplace import build_index, install
from agent_skills_marketplace.validation import validate_tree


SKILL = """---
name: demo-skill
description: A demo skill for tests.
metadata:
  version: \"1.0.0\"
---

# Demo
"""


class MarketplaceTests(unittest.TestCase):
    def make_skill(self, root, collection="demo", name="demo-skill", text=SKILL):
        path = root / collection / name
        path.mkdir(parents=True)
        (path / "SKILL.md").write_text(
            text.replace("demo-skill", name), encoding="utf-8"
        )
        return path

    def test_index_discovers_nested_skills_and_collections(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            self.make_skill(root)
            index = build_index(root, "Test Marketplace")

            self.assertEqual(index["name"], "Test Marketplace")
            self.assertEqual(index["collections"][0]["id"], "demo")
            self.assertEqual(index["skills"][0]["id"], "demo-skill")
            self.assertEqual(index["skills"][0]["version"], "1.0.0")

    def test_invalid_skill_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            self.make_skill(
                root,
                name="bad-skill",
                text=SKILL.replace("description: A demo skill for tests.", "description: <bad>"),
            )
            errors = validate_tree(root)
            self.assertTrue(any("angle brackets" in error for error in errors))

    def test_collection_install_flattens_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            target = Path(directory) / "installed"
            self.make_skill(root)
            self.make_skill(root, name="second-skill", text=SKILL)
            installed = install("collection:demo", root, target)

            self.assertEqual(
                sorted(path.name for path in installed),
                ["demo-skill", "second-skill"],
            )
            self.assertTrue((target / "demo-skill" / "SKILL.md").exists())


if __name__ == "__main__":
    unittest.main()

