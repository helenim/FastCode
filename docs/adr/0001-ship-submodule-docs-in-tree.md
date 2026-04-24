# ADR-0001: Ship submodule docs in the tree

**Status:** Accepted
**Date:** 2026-04-24
**Author:** Maarten Vanheusden

## Context

`README.md`'s "Documentation map" table links to `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/SECURITY.md`, `docs/MCP.md`, and `docs/OPERATIONS.md`. Inline prose elsewhere in the README links to the same files.

`docs/` has been listed in `.gitignore` since the initial commit (`6bfc599`), swept in alongside clearly-scratch entries (`association_agent.py`, `accurate_agent.py`, `benchmark/`, `examples/`). No commit message, comment, or ADR explains why docs were ignored; no submodule or sibling repo owns the files. The result: every doc link in `README.md` 404s on a fresh clone.

The `docs/` tree in the local working copy is well-formed — 11 markdown files, ~64 KB total, diataxis structure (`explanation/`, `how-to/`, `reference/`, `tutorials/`) plus five top-level operator references. `docs/MCP.md` was recently refreshed against `mcp_server.py` (commit `48f8fdd`). There is no content here that needs to remain out of version control.

Platform-level architecture decisions live in the parent e-Bridge monorepo at `docs/adr/` (see ADR-016 for this submodule's role). This ADR is scoped to the submodule's internal convention for where its operator documentation lives.

## Decision

1. Remove `docs/` from `.gitignore`.
2. Commit the existing `docs/` tree as-is.
3. Use this file (`docs/adr/0001-…`) to bootstrap a submodule-local ADR stream for future submodule-scoped decisions. Platform ADRs continue to live in the parent repo's `docs/adr/`.

Rejected: deleting the README references and relocating docs elsewhere (e.g. a wiki, the parent monorepo). The docs are operator-facing and tightly coupled to this submodule's entry points (`api.py`, `mcp_server.py`, `web_app.py`, `nanobot/`). Splitting them off would fragment the reader journey and break the "clone → read README → follow links" flow that the Documentation map promises.

## Consequences

### Positive

- README links resolve for fresh clones and on the forge web UI.
- Docs version with the code — an MCP or API change and its doc update land in the same commit, reviewed together.
- Establishes a submodule-local ADR stream without disturbing the platform ADR set.

### Negative

- `docs/` now counts against the submodule's repo size (currently ~64 KB; negligible).
- Future doc edits must pass the pre-commit hooks (`trailing-whitespace`, `end-of-file-fixer`, `mixed-line-ending`, `gitleaks`). Authors who previously edited untracked docs without friction will hit these checks.

### Risks

- If operator docs drift from `mcp_server.py` / `api.py`, the problem is now visible in PR diffs rather than hidden in an ignored directory. This is an improvement, but requires reviewer attention.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|--------------|
| Keep `docs/` ignored, delete README references | Smallest diff | Destroys ~64 KB of working operator docs that match code reality today | Content is valuable; the bug is the ignore rule, not the docs |
| Move docs to parent monorepo `docs/` | Co-locates with platform ADRs | Submodule-specific operator docs get buried in a platform-wide docs tree; broken links in this README persist | Wrong scope — these docs are submodule-internal, not platform-level |
| Publish docs to a wiki or static site | Decouples docs from repo | Adds infrastructure; READMEs linking to relative paths still 404 on clones | YAGNI — tree-shipped markdown already works for the reader journey |

## References

- Parent platform ADR: `../../../docs/adr/016-fastcode-code-intelligence.md`
- README documentation map: `../../README.md` (§ Documentation map)
- Commit that introduced the ignore: `6bfc599` (Initial commit)
- Commit that refreshed `docs/MCP.md`: `48f8fdd`
