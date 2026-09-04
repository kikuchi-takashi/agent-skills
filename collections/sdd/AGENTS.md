# SDD collection instructions

This collection contains portable, independently installable Agent Skills. Keep every package directly under `collections/sdd/<skill-name>/`, with `name` matching the directory. Use `sdd` for the main orchestrator and the `sdd-` prefix for every other SDD skill so flat installation does not introduce generic names.

Before changing the workflow, read `README.md`, `sdd-maintain/SKILL.md`, and every affected skill and packaged resource. Keep state.md phase values unprefixed (`specify`, `plan`, and so on); use prefixed names only for installed skill identifiers. Templates and prompts must stay inside the one skill that consumes them, with relative references.

Do not add client-specific configuration directories or require a particular agent's invocation API. Optional delegation may be described only with a direct fallback that preserves the same safety and approval boundaries. Historical files under `docs/genesis/` and `docs/trials/` are records, not current installation instructions.

Run `collections/sdd/scripts/validate`, then all verification required by the root `AGENTS.md`. Regenerate `marketplace.json` through the CLI and test `collection:sdd` installation into an empty flat target.
