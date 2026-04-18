# Roadmap: ebridge-fastcode

> Post-audit roadmap. Initial audit 2026-04-07, overlays 2026-04-15 and 2026-04-18.

---

## Short-Term (1-2 sprints)

### Security Hardening

- [ ] **Wire Keycloak auth into MCP server** — `ebridge-shared[auth]` is a
      pyproject dependency and `api.py` already attaches `_auth_dependencies` to
      every protected route; `mcp_server.py` has no equivalent. Add token
      validation middleware for HTTP/SSE transports.
- [x] **Implement `FASTCODE_ALLOWED_PATHS`** — `_is_path_allowed()` helper in
      `mcp_server.py:179`, enforced from `code_qa()` at `mcp_server.py:349`.
      Still needs to be set in all deployment configs.
- [x] **Partial ReDoS mitigation in `agent_tools.py`** — regex path wrapped in
      `try/except re.error` (line 177); literal path escapes via `re.escape()`
      (lines 187-190). Full mitigation (complexity check or `re2`) still needed.
- [ ] **Audit pickle usage** — 15 `pickle.load()` sites across
      `vector_store.py`, `retriever.py`, `cache.py`, `main.py`,
      `graph_builder.py`. Begin migrating `repo_overviews.pkl` → JSON
      (simplest structure).

### Test Infrastructure

- [ ] **Fix `__init__.py` eager imports** — `fastcode/__init__.py` still pulls
      `AnswerGenerator`, `IterativeAgent`, `FastCode`, etc. eagerly. Switch to
      `__getattr__` lazy pattern so test files can target submodules without
      requiring `anthropic` at collect time.
- [ ] **Raise coverage to 30%** — Current GitLab gate is 15%. Add unit tests
      for `retriever.py` (fusion logic), `path_utils.py`, and `agent_tools.py`.
- [x] **Add `httpx` to dev dependencies** — Present in both `requirements.txt`
      and `pyproject.toml` optional `[dev]`.

### Input Validation

- [x] **`code_qa()` bounds** — `mcp_server.py:455`: max 50,000 chars,
      max 20 repos, empty `repos` list rejected.
- [ ] **Validate `session_id` format** — Restrict to alphanumeric + hyphens,
      max 64 chars.
- [ ] **Add rate limiting** — Implement per-session or per-IP rate limits for
      HTTP/SSE transports.

---

## Medium-Term (1-2 months)

### Retrieval Quality

- [ ] **Switch to `voyage-code-3`** — Configured as the `api` provider in
      `config/config.yaml` but the default `embedding.provider` is still `local`
      (`paraphrase-multilingual-MiniLM-L12-v2`). Flip default, or document the
      deployment-time override.
- [x] **Code-aware BM25 tokenization** — `_code_tokenize()` in
      `retriever.py:20` splits camelCase, snake_case, dots, dashes, slashes.
      No stemming/stop-words yet.
- [ ] **Tune `min_similarity`** — Raise from 0.15 to 0.25-0.30 to reduce noise.
- [~] **Balanced fusion weights** — Config-level weights balanced at 0.5 each;
      default fusion method is RRF and ignores them. **Open drift**: code-level
      fallback defaults in `retriever.py:70-72` still read **0.6 / 0.3 / 0.1**
      when a config key is missing. Either align fallbacks or document the
      config-only nature of the balance.

### MCP Protocol

- [ ] **Default to Streamable HTTP** — SSE is deprecated in MCP spec. Change default transport from stdio to streamable-http for network deployments.
- [ ] **Add health check endpoint** — `/health` returns index stats, readiness status, and version. Required for container orchestration.

### Test Coverage

- [ ] **Raise coverage to 50%** — Add integration tests with local SentenceTransformer embedding (no external API needed).
- [ ] **Retrieval regression test** — Create a small synthetic Python repo, index it, query with known questions, assert correct files in top-k. Run in CI.
- [ ] **Malformed code tests** — Feed tree-sitter truncated, encoding-error, and binary files. Verify no crash.

---

## Long-Term (3-6 months)

### Vector Store Migration

- [ ] **Replace FAISS with Qdrant** — Benefits: native persistence, filtering, scalability, metadata queries, no pickle serialization.
  - Phase 1: Qdrant backend already exists at
    `fastcode/vector_stores/qdrant_store.py` (`QdrantVectorStore`). Selected
    via `config.yaml: vector_store.type: qdrant`. Make it the default.
  - Phase 2: Remove FAISS backend, eliminate pickle dependency for vectors.
  - Phase 3: Add Qdrant-native filtering (by repo, language, element type) to replace in-memory filtering.

### Security Maturation

- [ ] **Eliminate all `pickle.load()` calls** — Migrate to safetensors (vectors) + JSON/MessagePack (metadata).
- [ ] **Add RBAC** — Role-based access control for multi-tenant deployments.
- [ ] **Security audit of `iterative_agent.py`** — 163KB file with LLM-driven tool execution; needs dedicated review.

### CI/CD

- [ ] **Retrieval quality benchmarks in CI** — Run SWE-QA/LongCodeQA subset on every PR. Alert on regression.
- [ ] **Load testing** — Concurrent MCP connections, memory usage under indexing, FAISS search latency p99.
- [ ] **FAISS index reproducibility** — Verify that re-indexing the same repo produces identical results (deterministic embeddings + HNSW construction).

---

## Priority Matrix

| Priority | Item | Impact | Effort |
|----------|------|--------|--------|
| P0 | Wire Keycloak auth | Security | Medium |
| P0 | Fix `__init__.py` imports | DX/Testing | Low |
| P1 | Switch to voyage-code-3 | Quality | Low |
| ~~P1~~ | ~~Code-aware BM25 tokenization~~ | ~~Quality~~ | ~~Done~~ |
| P1 | Raise coverage to 50% | Reliability | Medium |
| P2 | Qdrant migration | Scalability | High |
| P2 | Eliminate pickle | Security | High |
| P2 | Retrieval regression CI | Quality | Medium |
