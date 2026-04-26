---
name: reindex
description: Re-index this repo in FastCode after significant code changes so semantic search and call graphs stay accurate. Triggered automatically by the PostToolUse stale-index hook on commit.
---

# reindex (2d-studio-ebridge-fastcode)

Use this skill when FastCode's index for **2d-studio-ebridge-fastcode** is stale — typically after a commit that touched many files, a refactor, or a schema change.

## When to invoke

- The PostToolUse `fastcode-stale-check` hook printed "FastCode index is stale" after your last commit.
- You suspect search results miss recently-added symbols.
- You added or renamed a file that other code depends on.

## How to reindex

Via the MCP `reindex_repo` tool (preferred — incremental when possible):

```jsonc
{
  "tool": "reindex_repo",
  "args": {
    "repo_source": "2d-studio-ebridge-fastcode"
  }
}
```

Or via the FastCode REST API:

```bash
curl -s -X POST http://localhost:5777/api/index \
  -H 'content-type: application/json' \
  -d '{"repo_path": "2d-studio-ebridge-fastcode"}'
```

After reindex completes, refresh the staleness marker so the hook stops nagging:

```bash
git -C 2d-studio-ebridge-fastcode rev-parse HEAD > 2d-studio-ebridge-fastcode/.ebridge/last-indexed-sha
```

## Tech stack tags for this repo

`python`

## When NOT to invoke

- The change is single-file and trivial — incremental indexing handles it on the next query.
- FastCode is not running on `localhost:5777` (start it first).
- You are mid-refactor and will commit again shortly — wait until the dust settles.
