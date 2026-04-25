# Reference — fastcode

Information-oriented reference material for FastCode entry points, MCP tools, and configuration.

## In this directory

To be populated. Authoritative reference pages currently live under the submodule root: [docs/API.md](../API.md), [docs/ARCHITECTURE.md](../ARCHITECTURE.md), [docs/MCP.md](../MCP.md), [docs/SECURITY.md](../SECURITY.md), [docs/OPERATIONS.md](../OPERATIONS.md).

## Reference material elsewhere

- [../README.md](../README.md) — REST API endpoints, MCP tool table, supported languages, LLM provider env blocks, Docker Compose structure.
- [../CLAUDE.md](../CLAUDE.md) — agent rules: three entry points, setuptools/pip build system, AST invariants, budget gating, coverage gate.

## Key reference tables

### Entry points and default ports

| Entry point | File | Default port | Docker port |
|-------------|------|--------------|-------------|
| Streamlit Web UI | `web_app.py` | 5777 | not exposed by default |
| REST API | `api.py` | 8000 | 8001 |
| MCP server | `mcp_server.py` | stdio (no network) | — |
| Nanobot gateway | `./run_nanobot.sh` | — | host 18791 → container 18790 |

### Core MCP tools

| Tool | Purpose |
|------|---------|
| `code_qa` | Multi-repo, multi-turn code Q&A (auto-clone + auto-index) |
| `list_indexed_repos` | Enumerate repos with FAISS/BM25/graph artifacts |
| `search_symbol` | Locate symbols (functions, classes, methods) by name |
| `get_repo_structure` | High-level structural summary of an indexed repo |
| `get_file_summary` | Per-file classes, functions, imports, and type hints |
| `get_call_chain` | Trace function/method call chains across the codebase |
| `reindex_repo` | Force full re-index after code changes |
| `list_sessions` / `get_session_history` / `delete_session` | Conversation session management |
| `delete_repo_metadata` | Drop `.faiss`, `_metadata.pkl`, `_bm25.pkl`, `_graphs.pkl` without deleting sources |

### Required environment variables

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | LLM credential (OpenAI, OpenRouter, or `ollama` placeholder) |
| `MODEL` | Model identifier (e.g. `gpt-5.2`, `google/gemini-3-flash-preview`, `qwen3-coder-30b_fastcode`) |
| `BASE_URL` | LLM endpoint (`https://api.openai.com/v1`, `https://openrouter.ai/api/v1`, `http://localhost:11434/v1`, …) |
| `FASTCODE_API_URL` | Injected into the Nanobot container so tools reach the FastCode REST API |

---
Last updated: 2026-04-18
Back: [submodule hub](../README.md) · [workspace hub](../../../docs/README.md)
