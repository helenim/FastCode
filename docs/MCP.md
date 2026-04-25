# MCP server — ebridge-fastcode

> Full reference for the MCP entry point. The README's [MCP Server
> section](../README.md#mcp-server-use-in-cursor--claude-code--windsurf)
> shows a quick-start; this doc is the operator reference.
> Line numbers intentionally omitted — tools are keyed by name and are
> stable; grep `mcp_server.py` for the current definitions.

---

## 1. Transports

| `--transport` | Env override | Port | Status | Use for |
|---------------|--------------|------|--------|---------|
| `stdio` | `FASTCODE_TRANSPORT=stdio` | n/a | **default** | Local IDEs (Cursor, Claude Desktop, Windsurf) — each client spawns its own process |
| `streamable-http` | `FASTCODE_TRANSPORT=streamable-http` | `--port` / `FASTCODE_MCP_PORT` (default `8080`), mount path `/mcp` | supported | Shared / remote deployments |
| `sse` | `FASTCODE_TRANSPORT=sse` | same as above | deprecated upstream, still wired | Legacy clients |

Launch example:

```bash
OPENAI_API_KEY=sk-… MODEL=your-model BASE_URL=https://api.openai.com/v1 \
  /path/to/FastCode/.venv/bin/python mcp_server.py \
  --transport streamable-http --port 8080
```

---

## 2. Tool catalogue (11 tools)

All tools live in `mcp_server.py` and are registered via `@mcp.tool()`.

| # | Tool | Summary |
|---|------|---------|
| 1 | `code_qa` | Core multi-turn Q&A over 1+ repos. Auto-clones URLs, auto-indexes, threads session state. |
| 2 | `list_sessions` | Enumerate conversation sessions with titles + turn counts. |
| 3 | `get_session_history` | Full Q&A transcript for a `session_id`. |
| 4 | `delete_session` | Drop a session and its history. |
| 5 | `list_indexed_repos` | Enumerate repos with persistent indexes on disk. |
| 6 | `delete_repo_metadata` | Remove `.faiss`, `_metadata.pkl`, `_bm25.pkl`, `_graphs.pkl` and the overview entry; keeps source. |
| 7 | `search_symbol` | Find functions/classes/methods by name across indexed repos. |
| 8 | `get_repo_structure` | High-level summary of one repo. |
| 9 | `get_file_summary` | Classes, functions, imports, type hints for a single file. |
| 10 | `get_call_chain` | Trace function/method call chains across the codebase. |
| 11 | `reindex_repo` | Force a full re-index of a repo (useful after code changes). |

### `code_qa` parameters

| Parameter | Required | Default | Notes |
|-----------|----------|---------|-------|
| `question` | yes | — | **Validated**: ≤ 50,000 chars, non-empty. |
| `repos` | yes | — | `list[str]`. **Validated**: ≤ 20 entries, non-empty, each gated by `FASTCODE_ALLOWED_PATHS` if set. |
| `multi_turn` | no | `True` | When true, prior Q&A from the same `session_id` feeds query rewriting + answer. |
| `session_id` | no | auto-generated | Returned in each response — pass back to continue the conversation. |

Validation sources: `code_qa` enforces bounds (≤ 20 repos, ≤ 50 000 chars);
local paths pass through `_is_path_allowed` before indexing. Grep
`mcp_server.py` for `_is_path_allowed` / `code_qa` to locate the current
definitions.

---

## 3. Environment variables

| Variable | Consumed by | Purpose |
|----------|-------------|---------|
| `OPENAI_API_KEY` | `llm_utils`, `answer_generator` | OpenAI-compatible API key |
| `MODEL` | same | Strong model id |
| `BASE_URL` | same | API root (OpenAI / OpenRouter / Ollama / Anthropic-compat) |
| `FAST_MODEL` | tiered routing in `answer_generator` | Optional cheap model (enable in `config.yaml: generation.routing.enabled`) |
| `EMBEDDING_API_KEY` | `embedding_providers/api.py` | Key for `voyage-code-3` / similar |
| `OLLAMA_BASE_URL` | `embedding_providers/ollama.py` | Local Ollama embedding endpoint |
| `QDRANT_URL` | `vector_stores/qdrant_store.py` | Qdrant server URL (overrides `config.yaml`) |
| `FASTCODE_TRANSPORT` | `mcp_server.py` entry | Default transport (`stdio` / `sse` / `streamable-http`) |
| `FASTCODE_MCP_PORT` | `mcp_server.py` entry | Default network port |
| `FASTCODE_ALLOWED_PATHS` | `mcp_server.py:_is_path_allowed` | Comma-separated absolute paths; empty = allow-all |

---

## 4. Client recipes

### Cursor (`~/.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "fastcode": {
      "command": "/path/to/FastCode/.venv/bin/python",
      "args": ["/path/to/FastCode/mcp_server.py"],
      "env": {
        "MODEL": "your-model",
        "BASE_URL": "https://api.openai.com/v1",
        "OPENAI_API_KEY": "sk-...",
        "FASTCODE_ALLOWED_PATHS": "/Users/me/work,/Users/me/dev"
      }
    }
  }
}
```

### Claude Code / Desktop (`claude_desktop_config.json`)

Same shape as Cursor. Alternatively:

```bash
claude mcp add fastcode -- \
  /path/to/FastCode/.venv/bin/python /path/to/FastCode/mcp_server.py
```

Ensure the same env vars are exported in your shell before invoking `claude`.

### Shared `streamable-http` deployment

```bash
FASTCODE_ALLOWED_PATHS=/srv/repos \
OPENAI_API_KEY=… MODEL=… BASE_URL=… \
/path/to/FastCode/.venv/bin/python mcp_server.py \
  --transport streamable-http --port 8080
```

Clients point at `http://host:8080/mcp`.

---

## 5. Known limitations

- **No authentication** — see [SECURITY.md §3 / SEC-002](SECURITY.md#3-known-residual-risks). Treat network-exposed deployments as privileged.
- **No `/health` endpoint** — `api.py` exposes `GET /health` but `mcp_server.py` does not. Container orchestrators should probe the MCP socket / port instead.
- **Session store is process-local** (see `main.py` session handling). Horizontal scaling requires sticky routing or migrating to a shared store.
- **Indexing is synchronous** inside the `code_qa` call path; for large repos prefer `reindex_repo` or the REST `/index` endpoint up front.

---

## 6. Related docs

- [ARCHITECTURE.md](ARCHITECTURE.md) — end-to-end request flow.
- [SECURITY.md](SECURITY.md) — threat surface and controls.
- [OPERATIONS.md](OPERATIONS.md) — ports, Docker, Nanobot.
- [../README.md#mcp-server-use-in-cursor--claude-code--windsurf](../README.md#mcp-server-use-in-cursor--claude-code--windsurf) — user-facing quick-start.
