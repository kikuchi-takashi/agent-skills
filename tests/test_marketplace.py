import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from agent_skills_marketplace.cli import main
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

    def make_bundle(self, root, bundle_id="bundle", skill_name="internal"):
        path = root / bundle_id
        skill = path / ".claude" / "skills" / skill_name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            SKILL.replace("demo-skill", skill_name), encoding="utf-8"
        )
        (path / "CLAUDE.md").write_text("# Bundle\n", encoding="utf-8")
        (path / "LICENSE").write_text("test license\n", encoding="utf-8")
        manifest = {
            "schemaVersion": "0.1",
            "id": bundle_id,
            "name": "Test Bundle",
            "description": "A coordinated test bundle for project installation.",
            "version": "1.0.0",
            "license": "MIT",
            "install": {
                "mode": "overlay",
                "paths": [".claude", "CLAUDE.md", "LICENSE"],
            },
        }
        (path / "bundle.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        return path

    def test_index_discovers_skills_and_collections(self):
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

    def test_install_refuses_to_replace_existing_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            target = Path(directory) / "installed"
            self.make_skill(root)
            existing = target / "demo-skill"
            existing.mkdir(parents=True)
            marker = existing / "keep.txt"
            marker.write_text("user data", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                install("demo-skill", root, target)

            self.assertEqual(marker.read_text(encoding="utf-8"), "user data")

    def test_force_replaces_existing_skill_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            target = Path(directory) / "installed"
            self.make_skill(root)
            existing = target / "demo-skill"
            existing.mkdir(parents=True)
            marker = existing / "old.txt"
            marker.write_text("old", encoding="utf-8")

            install("demo-skill", root, target, force=True)

            self.assertFalse(marker.exists())
            self.assertTrue((existing / "SKILL.md").exists())

    def test_collection_install_checks_all_destinations_before_copying(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            target = Path(directory) / "installed"
            self.make_skill(root)
            self.make_skill(root, name="second-skill", text=SKILL)
            (target / "second-skill").mkdir(parents=True)

            with self.assertRaises(FileExistsError):
                install("collection:demo", root, target)

            self.assertFalse((target / "demo-skill").exists())

    def test_install_target_inside_collection_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            skill = self.make_skill(root)

            with self.assertRaises(ValueError):
                install("demo-skill", root, root / "demo", force=True)

            self.assertTrue((skill / "SKILL.md").exists())

    def test_index_lists_bundle_without_individual_skill_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            self.make_skill(root)
            self.make_bundle(root)

            index = build_index(root, "Test Marketplace")

            self.assertEqual([item["id"] for item in index["skills"]], ["demo-skill"])
            self.assertEqual(index["schemaVersion"], "0.2")
            self.assertEqual(index["bundles"][0]["id"], "bundle")
            self.assertEqual(index["bundles"][0]["version"], "1.0.0")
            self.assertEqual(index["bundles"][0]["skills"], ["internal"])
            self.assertEqual(index["collections"][1]["kind"], "bundle")

    def test_discover_lists_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            self.make_skill(root)
            self.make_bundle(root)
            stdout = io.StringIO()

            with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
                result = main(["discover", "--root", str(root)])

            self.assertEqual(result, 0)
            self.assertIn("bundle:bundle", stdout.getvalue())

    def test_skill_names_are_unique_across_bundles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            self.make_skill(root)
            self.make_bundle(root, skill_name="demo-skill")

            errors = validate_tree(root)

            self.assertTrue(any("duplicate skill name" in error for error in errors))

    def test_bundle_install_overlays_declared_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            target = Path(directory) / "project"
            self.make_skill(root)
            self.make_bundle(root)

            installed = install("bundle:bundle", root, target)

            self.assertEqual(
                installed,
                [target / ".claude", target / "CLAUDE.md", target / "LICENSE"],
            )
            self.assertTrue(
                (target / ".claude" / "skills" / "internal" / "SKILL.md").is_file()
            )
            self.assertTrue((target / "CLAUDE.md").is_file())

    def test_bundle_only_root_is_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            self.make_bundle(root)

            self.assertEqual(validate_tree(root), [])

    def test_bundle_collision_is_checked_before_copying(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            target = Path(directory) / "project"
            self.make_skill(root)
            self.make_bundle(root)
            target.mkdir()
            (target / "CLAUDE.md").write_text("user file\n", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                install("bundle:bundle", root, target)

            self.assertFalse((target / ".claude").exists())
            self.assertEqual(
                (target / "CLAUDE.md").read_text(encoding="utf-8"), "user file\n"
            )

    def test_force_replaces_only_colliding_bundle_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            target = Path(directory) / "project"
            self.make_skill(root)
            self.make_bundle(root)
            target.mkdir()
            (target / "CLAUDE.md").write_text("old\n", encoding="utf-8")
            unrelated = target / ".claude" / "keep.txt"
            unrelated.parent.mkdir()
            unrelated.write_text("keep\n", encoding="utf-8")

            install("bundle:bundle", root, target, force=True)

            self.assertEqual(
                (target / "CLAUDE.md").read_text(encoding="utf-8"), "# Bundle\n"
            )
            self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep\n")

    def test_bundle_install_rejects_destination_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            target = Path(directory) / "project"
            external = Path(directory) / "external"
            self.make_skill(root)
            self.make_bundle(root)
            target.mkdir()
            external.mkdir()
            (target / ".claude").symlink_to(external, target_is_directory=True)

            with self.assertRaisesRegex(ValueError, "contains a symlink"):
                install("bundle:bundle", root, target, force=True)

            self.assertEqual(list(external.iterdir()), [])

    def test_collection_query_for_bundle_requires_explicit_bundle_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            self.make_skill(root)
            self.make_bundle(root)

            with self.assertRaisesRegex(ValueError, "use bundle:bundle"):
                install("collection:bundle", root, Path(directory) / "project")

    def test_bundle_rejects_unsafe_manifest_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            self.make_skill(root)
            bundle = self.make_bundle(root)
            manifest_path = bundle / "bundle.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["install"]["paths"] = ["../outside"]
            manifest_path.write_text(
                json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
            )

            errors = validate_tree(root)

            self.assertTrue(any("unsafe install path" in error for error in errors))

    def test_nested_skill_without_bundle_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            nested = root / "demo" / "extra" / "demo-skill"
            nested.mkdir(parents=True)
            (nested / "SKILL.md").write_text(SKILL, encoding="utf-8")

            errors = validate_tree(root)

            self.assertTrue(any("skill must be located" in error for error in errors))

    def test_invalid_collection_name_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            self.make_skill(root, collection="Bad_Name")

            errors = validate_tree(root)

            self.assertTrue(
                any("collection must be lowercase" in error for error in errors)
            )

    def test_symlink_in_portable_skill_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            skill = self.make_skill(root)
            outside = Path(directory) / "outside.txt"
            outside.write_text("external", encoding="utf-8")
            (skill / "linked.txt").symlink_to(outside)

            errors = validate_tree(root)

            self.assertTrue(
                any("symlinks are not allowed" in error for error in errors)
            )

    def test_index_check_detects_stale_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            output = Path(directory) / "marketplace.json"
            self.make_skill(root)
            output.write_text("{}\n", encoding="utf-8")

            stderr = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
                result = main(
                    [
                        "index",
                        "--root",
                        str(root),
                        "--output",
                        str(output),
                        "--name",
                        "Test Marketplace",
                        "--check",
                    ]
                )

            self.assertEqual(result, 1)
            self.assertIn("index is stale", stderr.getvalue())

    def test_index_check_accepts_current_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            output = Path(directory) / "marketplace.json"
            self.make_skill(root)
            output.write_text(
                json.dumps(
                    build_index(root, "Test Marketplace"),
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
                result = main(
                    [
                        "index",
                        "--root",
                        str(root),
                        "--output",
                        str(output),
                        "--name",
                        "Test Marketplace",
                        "--check",
                    ]
                )

            self.assertEqual(result, 0)
            self.assertIn("is current", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
