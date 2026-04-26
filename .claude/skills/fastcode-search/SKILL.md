---
name: fastcode-search
description: Search this repo's code with FastCode (semantic + BM25 hybrid via the FastCode REST API). Use when grep is too literal — e.g. "find auth handlers", "where is the payment workflow", "callers of UserRepository".
---

# fastcode-search (2d-studio-ebridge-fastcode)

Use this skill when you want richer-than-grep code search in **2d-studio-ebridge-fastcode**.

## When to invoke

- The user asks "where is X?" or "how does X work?" and a literal `grep`/`rg` would over- or under-match.
- You need callers/callees, type usage, or symbol-level context (use `code_qa` for narrative answers, `search_symbol` for surgical lookups).
- You want a fast confidence check before reading 5+ files manually.

## How to call

FastCode runs locally on **port 5777** (Streamlit/REST) and exposes:

```bash
# Semantic + BM25 hybrid, JSON response
curl -s -X POST http://localhost:5777/api/query \
  -H 'content-type: application/json' \
  -d '{"question": "<your question>", "repos": ["2d-studio-ebridge-fastcode"]}'
```

Or, when an MCP-aware tool is connected, call the `code_qa` tool directly:

```jsonc
{
  "tool": "code_qa",
  "args": {
    "question": "...",
    "repos": ["2d-studio-ebridge-fastcode"],
    "multi_turn": true
  }
}
```

Other useful MCP tools: `search_symbol`, `get_call_chain`, `get_repo_structure`, `get_file_summary`, `list_indexed_repos`.

## Tech stack tags for this repo

`python`

## When NOT to invoke

- Trivial single-token searches inside one open file (`grep` is fine).
- Pure documentation questions (use `kg-query` instead if available).
- The repo has not been indexed yet — run the `reindex` skill first or call `reindex_repo`.
