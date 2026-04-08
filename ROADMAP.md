# Roadmap: ebridge-fastcode

> Post-audit roadmap based on findings from 2026-04-07 audit

---

## Short-Term (1-2 sprints)

### Security Hardening

- [ ] **Wire Keycloak auth into MCP server** — `ebridge-shared[auth]` is already a dependency but not wired into `mcp_server.py`. Add token validation middleware for HTTP/SSE transports.
- [ ] **Deploy `FASTCODE_ALLOWED_PATHS`** — Set the env var in all deployment configs to restrict which local paths can be indexed.
- [ ] **Fix ReDoS in `agent_tools.py`** — Wrap `re.compile(search_term)` in try/except with a complexity check or use `re2` library.
- [ ] **Audit pickle usage** — Begin migrating `vector_store.py` metadata from pickle to JSON. Start with `repo_overviews.pkl` (simplest structure).

### Test Infrastructure

- [ ] **Fix `__init__.py` eager imports** — Use lazy imports (e.g., `__getattr__` pattern) so tests can import submodules without pulling in `anthropic`.
- [ ] **Raise coverage to 30%** — Add unit tests for `retriever.py` (fusion logic), `path_utils.py`, and `agent_tools.py`.
- [ ] **Add `httpx` to dev dependencies** — Unblocks `test_api.py`.

### Input Validation

- [ ] **Validate `session_id` format** — Restrict to alphanumeric + hyphens, max 64 chars.
- [ ] **Add rate limiting** — Implement per-session or per-IP rate limits for HTTP/SSE transports.

---

## Medium-Term (1-2 months)

### Retrieval Quality

- [ ] **Switch to `voyage-code-3`** — Change default embedding provider from `paraphrase-multilingual-MiniLM-L12-v2` to `voyage-code-3` (API provider). Update `config/config.yaml` defaults.
- [ ] **Code-aware BM25 tokenization** — Split camelCase, snake_case, dot notation before BM25 indexing. Estimated +15-20% keyword recall improvement.
- [ ] **Tune `min_similarity`** — Raise from 0.15 to 0.25-0.30 to reduce noise in results.
- [ ] **Document `graph_weight: 1.0`** — Clarify whether 2x vs semantic/keyword is intentional.

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
  - Phase 1: Qdrant backend already exists (`fastcode/vector_stores/qdrant.py`). Make it the default.
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
| P1 | Code-aware BM25 tokenization | Quality | Medium |
| P1 | Raise coverage to 50% | Reliability | Medium |
| P2 | Qdrant migration | Scalability | High |
| P2 | Eliminate pickle | Security | High |
| P2 | Retrieval regression CI | Quality | Medium |
