# Architecture — ebridge-fastcode

> Companion reference for [README.md](../README.md). Focus: runtime shape of
> the three entry points, data flow between layers, and the key on-disk
> artefacts. Reflects the tree at 2026-04-18.

---

## 1. Entry points

FastCode is a single Python package with **three concurrently-supported
entry points**, each mapping to a different audience:

| Entry point | File | Default port | Primary audience |
|-------------|------|--------------|------------------|
| Web UI (Streamlit) | `web_app.py` | `5777` | Human, local exploration |
| REST API (FastAPI) | `api.py` | `8000` (CLI) / `8001` (Docker) | Other services, scripts |
| MCP server | `mcp_server.py` | stdio / `--port` for `sse` / `streamable-http` | IDE assistants (Cursor, Claude, Windsurf) |
| CLI | `main.py` | n/a | Scripting / cron |

**Do not merge them.** Each has distinct auth, error-reporting, and lifecycle
semantics; collapsing them into a single handler has repeatedly introduced
regressions in session state and streaming.

---

## 2. Layered package layout

```
fastcode/
├── loader.py                 RepositoryLoader   (git clone / unpack zip / local path)
├── parser.py                 CodeParser         (facade over tree_sitter_parser)
├── tree_sitter_parser.py     TSParser           (AST + language detection)
├── indexer.py                CodeIndexer        (multi-level index construction)
├── embedder.py               Embedder           (local / ollama / api providers)
├── embedding_providers/                         provider implementations
├── vector_store.py           VectorStore        (FAISS default)
├── vector_stores/
│   └── qdrant_store.py       QdrantVectorStore  (opt-in replacement)
├── retriever.py              HybridRetriever    (semantic + BM25 + graph)
├── graph_builder.py          GraphBuilder       (call / dep / inherit / tests / co-change / type-usage)
├── call_extractor.py         |
├── import_extractor.py       |  specialised extractors fed into graph_builder
├── definition_extractor.py   |
├── symbol_resolver.py        |
├── module_resolver.py        |
├── repo_overview.py          RepositoryOverviewGenerator
├── repo_selector.py          RepositorySelector (LLM or embedding based)
├── query_processor.py        QueryProcessor     (expand / decompose / detect intent)
├── reranker.py               type-weight + optional cross-encoder
├── agent_tools.py            AgentTools         (listing, search, read, info — agency mode)
├── iterative_agent.py        IterativeAgent     (budget-aware multi-round retrieval)
├── answer_generator.py       AnswerGenerator    (LLM answer synthesis)
├── llm_utils.py              thin OpenAI-compatible client helpers
├── cache.py                  disk + semantic cache
├── main.py                   FastCode           (top-level orchestrator)
├── global_index_builder.py   cross-repo index fusion
├── path_utils.py             PathUtils          (security boundary)
└── utils.py                  misc helpers
```

`evaluation/` holds benchmark harnesses (SWE-QA, LongCodeQA, LOC-BENCH,
GitTaskBench) and is included in the `setuptools.packages.find` glob so
it's shipped alongside the library.

---

## 3. End-to-end request flow (`code_qa` style)

```
 user question
      │
      ▼
 QueryProcessor ─ expand / decompose / detect intent
      │
      ▼
 RepositorySelector ─ pick relevant repo(s) from overviews
      │
      ▼
 HybridRetriever
   ├─ VectorStore   (semantic, cosine, HNSW)
   ├─ BM25 index    (code-aware tokens: camel, snake, dots, slashes)
   └─ Graph expansion (call / import / inheritance edges, up to 2 hops)
      │
      ▼
 Fusion (default: RRF, k=60)
      │
      ▼
 Reranker (type-weight; optional cross-encoder)
      │
      ▼
 IterativeAgent (budget-aware)
   ├─ AgentTools    list / search / read / info
   └─ loop until confidence ≥ threshold or max_iterations hit
      │
      ▼
 AnswerGenerator ─ LLM synthesis with citations
      │
      ▼
 response (+ session persistence)
```

Budget gating is enforced inside `IterativeAgent` using five inputs:
confidence, query complexity, codebase size, cost, iteration count.
**Do not remove the gate** — it is what keeps token spend bounded.

---

## 4. On-disk artefacts

Under `data/`:

| Path | Producer | Notes |
|------|----------|-------|
| `data/vector_store/*.faiss` | `VectorStore` | FAISS HNSW index |
| `data/vector_store/*_metadata.pkl` | `VectorStore` | **pickle** — see [SECURITY.md](SECURITY.md) |
| `data/vector_store/*_bm25.pkl` | `HybridRetriever` | **pickle** |
| `data/vector_store/*_graphs.pkl` | `GraphBuilder` | **pickle** |
| `data/vector_store/repo_overviews.pkl` | `RepositoryOverviewGenerator` | **pickle** (first migration target → JSON) |
| `data/cache/*` | disk cache + semantic cache | TTL-gated |
| `logs/fastcode.log` | rotating log | path in `config.yaml` |
| `./repos/<name>` | `RepositoryLoader` | cloned/unzipped source trees |
| `./repo_backup/<name>` | `RepositoryLoader` | pre-overwrite safety copy |

`Qdrant` mode swaps the `*.faiss` + `*_metadata.pkl` pair for remote
collections (`fastcode`, `fastcode_overviews`) under the URL in
`config.yaml: vector_store.qdrant.url`.

---

## 5. Configuration surface

- `config/config.yaml` — retrieval, indexing, embeddings, agent, cache,
  evaluation, logging. **Authoritative** for non-secret tunables.
- `.env` — secrets + model routing (`OPENAI_API_KEY`, `MODEL`, `BASE_URL`,
  `FAST_MODEL` for tiered routing, `NANOBOT_MODEL` for Nanobot, optional
  `EMBEDDING_API_KEY` / `OLLAMA_BASE_URL`).
- `nanobot_config.json` — Feishu/WhatsApp credentials, Nanobot
  systemPrompt and channel enablement.
- `FASTCODE_ALLOWED_PATHS` — env-var allowlist for MCP local-path indexing.
  See [SECURITY.md](SECURITY.md).

Environment variables are consumed at module import time in
`answer_generator.py`, `llm_utils.py`, and the MCP entrypoint — changes
require a process restart.

---

## 6. Module-system integration

`module.ebridge.yaml` declares two e-Bridge UI widgets backed by the REST
API:

| widget_id | endpoint | layout | sandbox |
|-----------|----------|--------|---------|
| `fastcode-code-viewer` | `/api/fastcode/code` | 8×4 | `shadow_dom` |
| `fastcode-dependency-graph` | `/api/fastcode/graph` | 12×6 | `shadow_dom` |

Both activate lazily and run under `permissions.scope: workspace`.

---

## 7. Related docs

- [SECURITY.md](SECURITY.md) — auth, path safety, pickle risk.
- [MCP.md](MCP.md) — MCP tool catalogue and transport matrix.
- [OPERATIONS.md](OPERATIONS.md) — ports, env, Docker, Nanobot lifecycle.
- [../AUDIT-REPORT.md](../AUDIT-REPORT.md) — audit findings and remediation state.
- [../ROADMAP.md](../ROADMAP.md) — short/medium/long-term work.
