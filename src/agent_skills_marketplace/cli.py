"""Command-line interface for the Agent Skills marketplace."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from .discovery import load_skill, skill_files
from .marketplace import build_index, install, write_index
from .validation import validate_tree


def _common_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("collections"),
        help="root directory containing category directories (default: collections)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skills",
        description="Discover, validate, index, and install Agent Skills.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover_parser = subparsers.add_parser("discover", help="list discovered skills")
    _common_root(discover_parser)

    validate_parser = subparsers.add_parser("validate", help="validate skill files")
    _common_root(validate_parser)

    index_parser = subparsers.add_parser(
        "index", help="generate a marketplace JSON index"
    )
    _common_root(index_parser)
    index_parser.add_argument(
        "--output", type=Path, default=Path("marketplace.json")
    )
    index_parser.add_argument(
        "--name", default="Agent Skills Marketplace", help="marketplace display name"
    )
    index_parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the output does not match the generated index",
    )

    install_parser = subparsers.add_parser(
        "install", help="install one skill, its bundle, or an entire collection"
    )
    install_parser.add_argument(
        "query", help="skill name (bundle members expand) or collection:<category>"
    )
    _common_root(install_parser)
    install_parser.add_argument(
        "--target",
        type=Path,
        required=True,
        help="flat agent skills directory",
    )
    install_parser.add_argument(
        "--force", action="store_true", help="replace existing skill directories"
    )

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "discover":
            errors = validate_tree(args.root)
            if errors:
                for error in errors:
                    print("ERROR: {0}".format(error), file=sys.stderr)
                return 1
            for path in skill_files(args.root):
                record = load_skill(path, args.root)
                print("{0}/{1}\t{2}".format(record.collection, record.name, path))
            return 0

        if args.command == "validate":
            errors = validate_tree(args.root)
            if errors:
                for error in errors:
                    print("ERROR: {0}".format(error), file=sys.stderr)
                return 1
            print("OK: all skills are valid")
            return 0

        if args.command == "index":
            if args.check:
                expected = json.dumps(
                    build_index(args.root, args.name), ensure_ascii=False, indent=2
                ) + "\n"
                try:
                    actual = args.output.read_text(encoding="utf-8")
                except FileNotFoundError:
                    raise ValueError("index does not exist: {0}".format(args.output))
                if actual != expected:
                    raise ValueError(
                        "index is stale: regenerate {0}".format(args.output)
                    )
                print("OK: {0} is current".format(args.output))
                return 0
            write_index(args.root, args.output, args.name)
            print("Wrote {0}".format(args.output))
            return 0

        if args.command == "install":
            installed = install(args.query, args.root, args.target, args.force)
            for path in installed:
                print("Installed {0}".format(path))
            return 0

    except (ValueError, FileExistsError, OSError) as exc:
        print("ERROR: {0}".format(exc), file=sys.stderr)
        return 1

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
