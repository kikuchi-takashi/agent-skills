# Contributing

Distributable skills belong at `collections/<collection>/<skill-name>/SKILL.md`. Before contributing, read `AGENTS.md` and `docs/ARCHITECTURE.md`; scoped `AGENTS.md` files override only their subtree.

For a normal skill contribution:

1. Confirm the lowercase kebab-case skill name is unique across `collections/`.
2. Keep the package independently copyable. Include optional resources only when used, and avoid symlinks.
3. Write a discriminating `description` that states both capability and activation context.
4. Review scripts and external material for safety, provenance, compatible licensing, and retained notices.
5. Run the validation commands in `AGENTS.md` and regenerate `marketplace.json` through the CLI.
6. Inspect the full diff and report behavior, validation evidence, index impact, and any compatibility risk.

Client-specific configuration and project overlays are outside this marketplace format. Package every distributable capability as an independent Agent Skills directory.
