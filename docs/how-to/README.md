# How-to guides — fastcode

Task-oriented recipes for operating the FastCode code-intelligence stack (Web UI, REST API, MCP server, Nanobot bridge).

## Guides in this directory

No guides written yet — planned set below. Existing operational references live under the submodule root (`docs/API.md`, `docs/ARCHITECTURE.md`, `docs/MCP.md`, `docs/OPERATIONS.md`, `docs/SECURITY.md`).

## Planned how-to guides

- **How to register FastCode as an MCP server in Cursor / Claude Code / Windsurf** — wire `.venv/bin/python mcp_server.py` with the required `OPENAI_API_KEY`, `MODEL`, and `BASE_URL` env vars so `code_qa` and the nine supporting tools become available to an IDE.
- **How to run the MCP server over SSE transport for remote agents** — start `mcp_server.py --transport sse --port 8080` and front it with the workspace reverse proxy (ADR-041).
- **How to reindex a repository after a large refactor** — call the `reindex_repo` MCP tool or `POST /index?force=true` on the REST API, keeping prior `repo_overviews.pkl` entries.
- **How to enable Keycloak auth on the REST API** — install the workspace `ebridge_auth` package so `api.py` enforces JWT validation without code changes.
- **How to deploy the Nanobot + Feishu + WhatsApp bridge** — use `./run_nanobot.sh` to build images (FastCode `8001`, Nanobot `18791`), populate `nanobot_config.json` with Feishu `appId`/`appSecret`, and register the five `fastcode_*` tools via `FASTCODE_API_URL`.
- **How to swap LLM providers without reindexing** — change `MODEL` / `BASE_URL` in `.env` (OpenAI, OpenRouter, Ollama) while preserving `.faiss`, `_metadata.pkl`, `_bm25.pkl`, and `_graphs.pkl` on disk.
- **How to clean metadata without deleting source** — invoke `delete_repo_metadata` to drop FAISS/BM25/graph artifacts and the `repo_overviews.pkl` entry while keeping the cloned repo tree.

---
Last updated: 2026-04-18
Back: [submodule hub](../README.md) · [workspace hub](../../../docs/README.md)
