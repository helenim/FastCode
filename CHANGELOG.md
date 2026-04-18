# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The runtime surface reports itself as `2.0.0` (`fastcode.__version__`). The
Python packaging version in `pyproject.toml` is pinned at `0.0.0` because this
module ships as a submodule — `requirements.txt` is the CI source of truth and
the submodule pointer is the release artifact.

## [Unreleased]

### Security

- Path traversal: `is_safe_path()` now uses an `os.sep`-aware `_is_within_root()`
  check, closing the prefix-collision gap (`/tmp/repo_evil` ≠ `/tmp/repo`).
- Null-byte injection rejected at the top of `is_safe_path()`.
- MCP server: `FASTCODE_ALLOWED_PATHS` env-var allowlist gates which local
  paths `code_qa()` may index; enforced via `_is_path_allowed()` in
  `mcp_server.py`.
- MCP `code_qa()` input validation: max 50,000 chars for `question`, max 20
  repos per call, empty `repos` list rejected.
- `agent_tools.py` regex path now wraps `re.compile()` in `try/except re.error`;
  literal-search path pre-escapes input with `re.escape()`.
- bandit HIGH on MD5 resolved by tagging `usedforsecurity=False` (workspace-wide
  hygiene sweep).

### Added

- `fastcode/vector_stores/qdrant_store.py` — Qdrant backend (`QdrantVectorStore`)
  alongside the default FAISS store; selectable via `config.yaml: vector_store.type`.
- `tests/test_security.py` (17 cases) and `tests/test_monkey.py` (42 cases)
  covering path traversal, null bytes, injection, unicode edges, oversized and
  concurrent inputs.
- Additional test suites: `test_evaluation`, `test_embedding_providers`,
  `test_graph_enhanced_rag`, `test_graph_expansion`, `test_incremental_indexing`,
  `test_incremental_indexing_regressions`, `test_language_expansion`,
  `test_metadata_migration`, `test_model_routing`, `test_reranker`,
  `test_semantic_cache`, `test_tree_sitter_parser`, `test_vector_stores`.
- `nanobot/bridge/` — Node.js WhatsApp gateway
  (`nanobot-whatsapp-bridge`, Baileys). CI job: `whatsapp-bridge`.
- `module.ebridge.yaml` — micro-kernel module manifest declaring two
  `ui_widgets` (`fastcode-code-viewer`, `fastcode-dependency-graph`).
- Keycloak-ready optional auth via `ebridge-shared[auth]` dependency in
  `pyproject.toml` — wired into `api.py` route dependencies when importable
  (MCP wiring still pending).

### Changed

- BM25 tokenisation now code-aware (`_code_tokenize`): splits camelCase,
  snake_case, dots, dashes and slashes before indexing.
- `config/config.yaml`: fusion weights balanced (`semantic_weight: 0.5`,
  `keyword_weight: 0.5`, `graph_weight: 0.5`). Default `fusion_method: "rrf"`.
  Note: code-level fallback defaults in `HybridRetriever.__init__` still read
  0.6/0.3/0.1 when keys are missing — tracked in [ROADMAP](ROADMAP.md).
- Embedding providers: `local` (SentenceTransformer), `ollama` and `api`
  (voyage-code-3, nomic-embed-code) all selectable from `config.yaml`.

### Documentation

- Rewritten [AUDIT-REPORT.md](AUDIT-REPORT.md) with accurate line numbers and
  test counts (19 files).
- New technical references under [docs/](docs/): `ARCHITECTURE.md`,
  `SECURITY.md`, `MCP.md`, `OPERATIONS.md`.
- [README.md](README.md) module-system section aligned with
  `module.ebridge.yaml` (widgets, not `nats_handler`).

## [2.0.0] — original upstream

### Added

- AST-based code indexing for 8+ languages (Python, JS/TS, Java, Go, C/C++, Rust, C#)
- Hybrid search engine (semantic embeddings + BM25 keyword search)
- Multi-layer code graphs (call, dependency, inheritance)
- Multi-turn code QA with session management
- Three entry points: Streamlit Web UI, REST API, MCP server
- MCP tools (`code_qa`, `search_symbol`, `get_repo_structure`, `get_call_chain`,
  `list_indexed_repos`, `list_sessions`, `get_session_history`, `delete_session`,
  `delete_repo_metadata`, `get_file_summary`, `reindex_repo` — 11 total)
- Nanobot + Feishu/Lark bot integration
- Budget-aware query decision making
- REST API with repository management, streaming queries, and caching
