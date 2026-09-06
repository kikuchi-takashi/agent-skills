import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

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
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class MarketplaceTests(unittest.TestCase):
    def make_skill(self, root, collection="demo", name="demo-skill", text=SKILL):
        path = root / collection / name
        path.mkdir(parents=True)
        (path / "SKILL.md").write_text(
            text.replace("demo-skill", name), encoding="utf-8"
        )
        return path

    def test_index_discovers_skills_and_collections(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            self.make_skill(root)
            index = build_index(root, "Test Marketplace")

            self.assertEqual(index["name"], "Test Marketplace")
            self.assertEqual(index["schemaVersion"], "0.1")
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

    def test_installing_bundle_member_installs_complete_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            bundled = SKILL.replace(
                '  version: "1.0.0"',
                '  version: "1.0.0"\n  bundle: demo-suite',
            )
            self.make_skill(root, name="demo-create", text=bundled)
            self.make_skill(root, name="demo-review", text=bundled)
            target = Path(directory) / "installed"

            installed = install("demo-create", root, target)

            self.assertEqual(
                sorted(path.name for path in installed),
                ["demo-create", "demo-review"],
            )

    def test_bundle_install_checks_all_destinations_before_copying(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            bundled = SKILL.replace(
                '  version: "1.0.0"',
                '  version: "1.0.0"\n  bundle: demo-suite',
            )
            self.make_skill(root, name="demo-create", text=bundled)
            self.make_skill(root, name="demo-review", text=bundled)
            target = Path(directory) / "installed"
            (target / "demo-review").mkdir(parents=True)

            with self.assertRaises(FileExistsError):
                install("demo-create", root, target)

            self.assertFalse((target / "demo-create").exists())

    def test_bundle_install_copy_failure_leaves_existing_skills_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            bundled = SKILL.replace(
                '  version: "1.0.0"',
                '  version: "1.0.0"\n  bundle: demo-suite',
            )
            self.make_skill(root, name="demo-create", text=bundled)
            self.make_skill(root, name="demo-review", text=bundled)
            target = Path(directory) / "installed"
            for name in ("demo-create", "demo-review"):
                existing = target / name
                existing.mkdir(parents=True)
                (existing / "old.txt").write_text("old", encoding="utf-8")

            real_copytree = shutil.copytree
            copies = 0

            def fail_second_copy(source, destination):
                nonlocal copies
                copies += 1
                if copies == 2:
                    raise OSError("simulated copy failure")
                return real_copytree(source, destination)

            with mock.patch(
                "agent_skills_marketplace.marketplace.shutil.copytree",
                side_effect=fail_second_copy,
            ):
                with self.assertRaisesRegex(OSError, "simulated copy failure"):
                    install("demo-create", root, target, force=True)

            for name in ("demo-create", "demo-review"):
                self.assertEqual(
                    (target / name / "old.txt").read_text(encoding="utf-8"), "old"
                )

    def test_bundle_install_commit_failure_restores_all_existing_skills(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            bundled = SKILL.replace(
                '  version: "1.0.0"',
                '  version: "1.0.0"\n  bundle: demo-suite',
            )
            self.make_skill(root, name="demo-create", text=bundled)
            self.make_skill(root, name="demo-review", text=bundled)
            target = Path(directory) / "installed"
            for name in ("demo-create", "demo-review"):
                existing = target / name
                existing.mkdir(parents=True)
                (existing / "old.txt").write_text(name, encoding="utf-8")

            real_replace = os.replace

            def fail_second_commit(source, destination):
                source_path = Path(source)
                if (
                    source_path.parent.name == "staged"
                    and source_path.name == "demo-review"
                ):
                    raise OSError("simulated commit failure")
                return real_replace(source, destination)

            with mock.patch(
                "agent_skills_marketplace.marketplace.os.replace",
                side_effect=fail_second_commit,
            ):
                with self.assertRaisesRegex(OSError, "simulated commit failure"):
                    install("demo-create", root, target, force=True)

            for name in ("demo-create", "demo-review"):
                self.assertEqual(
                    (target / name / "old.txt").read_text(encoding="utf-8"), name
                )

    def test_failed_rollback_retains_recovery_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            bundled = SKILL.replace(
                '  version: "1.0.0"',
                '  version: "1.0.0"\n  bundle: demo-suite',
            )
            self.make_skill(root, name="demo-create", text=bundled)
            self.make_skill(root, name="demo-review", text=bundled)
            target = Path(directory) / "installed"
            for name in ("demo-create", "demo-review"):
                existing = target / name
                existing.mkdir(parents=True)
                (existing / "old.txt").write_text(name, encoding="utf-8")

            real_replace = os.replace

            def fail_commit_and_restore(source, destination):
                source_path = Path(source)
                if source_path.name == "demo-review" and source_path.parent.name in (
                    "staged",
                    "backup",
                ):
                    raise OSError("simulated transaction failure")
                return real_replace(source, destination)

            with mock.patch(
                "agent_skills_marketplace.marketplace.os.replace",
                side_effect=fail_commit_and_restore,
            ):
                with self.assertRaisesRegex(OSError, "recovery data retained at"):
                    install("demo-create", root, target, force=True)

            transactions = list(target.glob(".skills-install-*"))
            self.assertEqual(len(transactions), 1)
            retained = transactions[0] / "backup" / "demo-review" / "old.txt"
            self.assertEqual(retained.read_text(encoding="utf-8"), "demo-review")

    def test_index_exposes_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            bundled = SKILL.replace(
                '  version: "1.0.0"',
                '  version: "1.0.0"\n  bundle: demo-suite',
            )
            self.make_skill(root, name="demo-create", text=bundled)
            self.make_skill(root, name="demo-review", text=bundled)

            index = build_index(root, "Test Marketplace")

            self.assertEqual(
                {skill["bundle"] for skill in index["skills"]}, {"demo-suite"}
            )

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

    def test_install_refuses_to_replace_broken_symlink_without_force(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            target = Path(directory) / "installed"
            self.make_skill(root)
            target.mkdir()
            destination = target / "demo-skill"
            destination.symlink_to(Path(directory) / "missing")

            with self.assertRaises(FileExistsError):
                install("demo-skill", root, target)

            self.assertTrue(destination.is_symlink())

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

    def test_sdd_collection_installs_as_portable_skills(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "installed"

            installed = install(
                "collection:sdd", PROJECT_ROOT / "collections", target
            )

            self.assertEqual(len(installed), 15)
            self.assertTrue((target / "sdd" / "SKILL.md").is_file())
            self.assertTrue((target / "sdd-improver" / "SKILL.md").is_file())
            self.assertTrue((target / "sdd-specify" / "template.md").is_file())

    def test_nested_skill_is_rejected(self):
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

    def test_singleton_bundle_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "collections"
            bundled = SKILL.replace(
                '  version: "1.0.0"',
                '  version: "1.0.0"\n  bundle: demo-suite',
            )
            self.make_skill(root, text=bundled)

            errors = validate_tree(root)

            self.assertTrue(
                any("must contain at least two skills" in error for error in errors)
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
