---
name: marketplace-skill-maintainer
description: Add, update, remove, or review distributable skills and regenerate the index in this Agent Skills marketplace repository. Use for marketplace package maintenance; do not use for merely using an installed skill.
---

# Marketplace Skill Maintainer

Maintain this repository's portable skill catalog without widening the user's requested change.

## Establish scope

1. Read the root `AGENTS.md`, `README.md`, and `docs/ARCHITECTURE.md`, plus scoped instructions and the complete target package.
2. Inspect `git status --short`. Treat existing changes as user work and keep unrelated files untouched.
3. Classify the request as add, update, explicit delete/rename, review, or index repair. Do not turn review into modification or deletion into a broader cleanup.
4. Confirm that the target remains a standalone portable skill. For `collections/sdd/`, also follow its local `AGENTS.md` and namespacing rules.

## Maintain a portable skill

- Use `collections/<collection>/<skill-name>/SKILL.md` exactly. Both names are lowercase kebab-case; the skill name is globally unique, at most 64 characters, and matches frontmatter `name`.
- Make `description` say what the skill does and when it should activate. Avoid generic verbs and triggers that overlap unrelated work.
- Keep the entry point concise. Add `references/` only for conditional detail, `scripts/` only for reusable deterministic behavior, and `assets/` only for output material.
- Make every reference relative to the skill directory and ensure the package still works when copied alone.
- Preserve authorization boundaries. Never instruct an agent to delete, overwrite, publish, push, or send data without an explicit request at that stage.
- Inspect scripts and external material before use. Record compatible provenance and required notices; do not assume a frontmatter license proves ownership.

For a review-only request, report findings with file locations and do not edit. For a removal or rename, proceed only when explicitly requested and search the repository for consumers first.

## Verify and index

Run the repository-required commands from `AGENTS.md`. Validate a new skill with an available Agent Skills validator as an additional check. Run any new or changed script against a representative success case and a safe failure case when applicable.

Regenerate `marketplace.json` only through the CLI; never patch it by hand. Inspect the resulting diff to ensure unrelated skills, metadata, and user changes were not altered. Report commands and actual outcomes, including any validation that could not run.
