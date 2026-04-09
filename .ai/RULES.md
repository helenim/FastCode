# e-Bridge FastCode — Agent Instructions

This file is the single source of truth for AI agent rules in this project workspace. IDE-specific files (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.cursorrules`, `.cursor/rules/project.mdc`) are symlinks to `.ai/RULES.md`.

---

## Project Overview

**FastCode** is a code understanding and intelligence framework providing AST-based indexing, hybrid search (semantic + BM25), cross-repo reasoning, and multi-turn code QA. It exposes three interfaces: a Streamlit Web UI, a REST API, and an MCP server for IDE integration.

### Multi-Repo Context

This is the **fastcode** repo (package name: `fastcode-ebridge`). Related repositories:

- `2d-studio-ebridge-agent-runtime` — Orchestration layer (consumes MCP tools)
- `2d-studio-ebridge-observability` — Monitoring
- `2d-studio-ebridge-agentic` — Shared agentic framework

**The README.md (1050+ lines) is the comprehensive reference.** This CLAUDE.md focuses on agent-specific rules and constraints — refer to README for detailed API docs, benchmarks, and setup instructions.

---

## Critical Architecture Rules

### Three Entry Points

```
web_app.py  → Streamlit Web UI (port 5777)
api.py      → REST API (port 8000 local / 8001 Docker)
mcp_server.py → MCP server (stdio transport for IDE integration)
```

**Each entry point serves a different audience.** Do not merge them.

### Build System: setuptools + requirements.txt

This module uses **setuptools** (not hatchling) and **requirements.txt** (not uv). **Install with `pip install -e .`**. The `requirements.txt` is the CI source of truth.

### Semantic-Structural Code Representation

FastCode uses a hierarchical approach:
1. **AST Parsing** — multi-level indexing (files, classes, functions, docs) for 8+ languages
2. **Hybrid Index** — semantic embeddings + BM25 keyword search
3. **Multi-Layer Graphs** — call graph, dependency graph, inheritance graph
4. **Two-Stage Search** — relevance finding + ranking

**Do NOT bypass the AST parser** — all code understanding flows through structured code units.

### Supported Languages

Python, JavaScript/TypeScript, Java, Go, C/C++, Rust, C#. Language support is determined by AST parser availability.

### MCP Tools

Primary tool: `code_qa` — multi-turn QA on 1+ repos (auto-detect indexed, auto-clone URLs).

Supporting tools: `list_indexed_repos`, `list_sessions`, `get_session_history`, `delete_session`, `search_symbol`, `get_repo_structure`, `get_file_summary`, `get_call_chain`, `reindex_repo`, `delete_repo_metadata`.

### Budget-Aware Decision Making

The query engine considers: confidence, query complexity, codebase size, cost, and iteration count. **Do NOT remove budget gating** — it prevents runaway token spend.

### Nanobot + Feishu Integration

`docker-compose.yml` includes a Nanobot service (Feishu/Lark bot) alongside FastCode. Config in `nanobot_config.json`. Management via `run_nanobot.sh`.

---

## Repository Structure

Refer to README for the full directory tree. Key paths:

```
fastcode/           # Core library (AST parsing, indexing, search, graphs)
evaluation/         # Benchmark evaluation
api.py              # REST API entry point
web_app.py          # Streamlit Web UI entry point
mcp_server.py       # MCP server entry point
main.py             # CLI entry point
docs/
  API.md            # REST API reference
```

---

## Common Development Commands

```bash
# Install (uses pip, not uv)
pip install -e .
pip install -e ".[dev]"

# Run Web UI
python web_app.py --port 5777

# Run REST API
python api.py --port 8000

# Run MCP server (stdio)
python mcp_server.py

# CLI query
python main.py query --repo-path /path/to/repo --query "How does auth work?"

# Tests
pytest tests/ -v

# Docker (with Nanobot)
docker compose up
./run_nanobot.sh status
```

---

## Ports

| Service | Port | Context |
|---------|------|---------|
| Web UI | 5777 | Local development |
| REST API | 8000 | Local CLI |
| REST API | 8001 | Docker / workspace |
| Nanobot | 18791 | Feishu/Lark gateway |

---

## Key Points for AI Agents

- **README is the primary reference** (1050+ lines) — this CLAUDE.md is supplementary
- Uses **setuptools + pip**, not hatchling/uv
- Three entry points serve different audiences — keep them separate
- AST parsing is the foundation — all code intelligence flows through it
- Budget-aware gating prevents runaway costs — do not disable
- MCP server uses stdio transport — no network port by default
- Coverage gate: **15%** (low — focus on integration correctness over unit coverage)
- `run_nanobot.sh` manages the Feishu bot lifecycle (build, restart, logs, status, clean)
