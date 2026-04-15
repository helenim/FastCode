## 2026-04-15 Refactor Status Update

This submodule was touched by the 2026-Q2 audit refactor session. Key changes:

- **KI-75 (REMEDIATED)**: nanobot CLI — 6 commands are now fully implemented (previously stubs). See `nanobot/` directory.
- **KI-76 (REMEDIATED)**: Multi-repo graph merging — cross-repo reasoning path is now implemented and exercised by tests.
- **FINDING-F03-002 / bandit HIGH (RESOLVED 2026-04-15)**: The 1× MD5 usage in `fastcode/utils.py:352` is now tagged `usedforsecurity=False` — bandit no longer flags it. This was part of the workspace-wide bandit hygiene sweep (Agent 4).

Authoritative source: `_TODO_audit_plan/FINAL-AUDIT-STATUS-2026-04-15.md`. See also `_TODO_audit_plan/ACTION-PLAN-2026-04-15.md`.

---

# Audit Report: ebridge-fastcode

> **Date**: 2026-04-07 (Q2 ecosystem-audit overlay added 2026-04-15)
> **Scope**: `2d-studio-ebridge-fastcode` — Python code intelligence service
> **Auditor**: Automated engineering audit
> **Classification**: Internal

---

## Executive Summary

FastCode is a **hybrid FAISS + BM25 retrieval system** with tree-sitter AST parsing, exposed via MCP (Model Context Protocol). The audit identified **3 critical security vulnerabilities** (now fixed), **2 medium security risks** (documented), and significant test coverage gaps.

**Key findings:**
- `is_safe_path()` had a prefix-collision bypass allowing path traversal (FIXED)
- MCP server had zero input validation on `code_qa()` (FIXED)
- No authentication on the MCP server (DOCUMENTED — needs Keycloak wiring)
- 10 of 13 test files fail to collect due to eager imports in `__init__.py`
- Default embedding model is general-purpose, not code-specialized

---

## 1. Security Findings

### SEC-001: Path Traversal via Prefix Collision [CRITICAL — FIXED]

**File**: `fastcode/path_utils.py:263`
**Vulnerability**: `is_safe_path()` used `abs_path.startswith(self.repo_root)`, allowing paths like `/tmp/repo_evil/secret` to pass when repo_root is `/tmp/repo`.
**Fix**: Replaced with `_is_within_root()` using `abs_path == self.repo_root or abs_path.startswith(self.repo_root + os.sep)`.
**Test**: `tests/test_security.py::TestPathTraversal::test_prefix_collision`

### SEC-001b: Null Byte Injection [CRITICAL — FIXED]

**File**: `fastcode/path_utils.py:258`
**Vulnerability**: Null bytes in paths (`src/main.py\x00.txt`) were not rejected. Null bytes can truncate paths in C-level syscalls, bypassing extension checks.
**Fix**: Added explicit null byte rejection at the top of `is_safe_path()`.
**Test**: `tests/test_security.py::TestPathTraversal::test_null_byte`

### SEC-002: No MCP Authentication [HIGH — DOCUMENTED]

**File**: `mcp_server.py`
**Issue**: MCP server exposes 11 tools with zero authentication. The `repos` parameter in `code_qa()` accepts arbitrary filesystem paths — an attacker can index `/etc/`, `/home/`, or any readable directory.
**Mitigation added**: `FASTCODE_ALLOWED_PATHS` environment variable restricts which local paths can be indexed (comma-separated allowlist). The `_is_path_allowed()` helper enforces this at `mcp_server.py:179`.
**Recommendation**: Wire Keycloak authentication from `ebridge-shared[auth]` into the MCP server.

### SEC-003: Input Validation Gaps [HIGH — FIXED]

**File**: `mcp_server.py:226`
**Vulnerability**: `code_qa()` had no limits on question length, repos list size, or session_id format.
**Fix**: Added validation: max 50K chars for question, max 20 repos, reject empty repos list.

### SEC-004: Pickle Deserialization [MEDIUM — DOCUMENTED]

**Files**: `vector_store.py` (6 sites), `retriever.py` (2), `cache.py` (3), `main.py` (2), `graph_builder.py` (2) — 15 total `pickle.load()` calls, all suppressed with `# nosec B301`.
**Risk**: If an attacker can place a malicious `.pkl` file in `data/vector_store/` or `data/cache/`, arbitrary code execution results.
**Recommendation**: Migrate to `safetensors` for vector data and JSON/MessagePack for metadata.

### SEC-005: ReDoS in Agent Tools [MEDIUM — PARTIALLY MITIGATED]

**File**: `fastcode/agent_tools.py`
**Issue**: `re.compile(search_term)` with user-provided input is vulnerable to catastrophic backtracking (e.g., `(a+)+b` pattern).
**Mitigation**: `re.compile()` is now wrapped in a `try-except re.error` block (line ~177) with a graceful error return. When `use_regex=False`, input is escaped via `re.escape()`.
**Test**: `tests/test_security.py::TestReDoS::test_catastrophic_backtracking_pattern` (xfail — catastrophic backtracking itself is not prevented, only compilation errors are caught).
**Recommendation**: Add a regex complexity check or use the `re2` library for guaranteed linear-time matching.

---

## 2. Retrieval Quality Findings

### RET-001: BM25 Tokenization [RESOLVED]

**File**: `fastcode/retriever.py:20-37`
**Status**: **FIXED** — The `_code_tokenize()` helper now splits camelCase, snake_case, dots, dashes, and slashes before BM25 indexing. Example: `getUserById` → `['get', 'user', 'by', 'id']`.
**Note**: No stemming or stop-word removal yet, but the code-aware splitting addresses the primary recall gap.

### RET-002: Default Embedding Model Not Code-Specialized

**Config**: `config/config.yaml`
**Current**: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384-dim, multilingual text model)
**Issue**: General-purpose model, NOT optimized for code retrieval.
**Available**: `voyage-code-3` configured as API provider but not default.
**Recommendation**: Switch default to `voyage-code-3` or `nomic-embed-code`.

### RET-003: Fusion Weight Configuration [RESOLVED]

**Config**: `config/config.yaml`
**Status**: Weights are now balanced: `semantic_weight: 0.5`, `keyword_weight: 0.5`, `graph_weight: 0.5`. The default `fusion_method` is `"rrf"` (Reciprocal Rank Fusion), which does not use these weights — they only apply to the legacy `"weighted_linear"` fusion method.
**Remaining**: `min_similarity: 0.15` is still low — cosine similarity below 0.3 is typically noise.

### RET-004: RRF Fusion is Well-Implemented

**File**: `fastcode/retriever.py:980-1038`
**Assessment**: The RRF implementation follows the standard formula `score(d) = sum(1 / (k + rank + 1))` with k=60. This is correct and well-documented. The weighted linear combination is preserved as a legacy alternative.

---

## 3. Test Coverage Analysis

### Current State

| Metric | Value |
|--------|-------|
| Total test files | 16 (14 existing + 2 new) |
| Collectible test files | 5 of 16 |
| Tests passing | 77 (35 existing + 42 new) |
| Tests failing | 8 (matryoshka — missing `anthropic` dep) |
| Collection errors | 10 files (eager `__init__.py` imports) |
| CI coverage threshold | 15% (GitLab) / 50% (GitHub Actions) |

### Root Cause of Collection Failures

`fastcode/__init__.py` eagerly imports all modules including `AnswerGenerator` which requires `anthropic`. Any test importing from `fastcode.*` triggers this chain. The MCP server tests work because they mock the entire `fastcode` package.

### Modules with Zero Test Coverage

| Module | Lines | Criticality |
|--------|-------|-------------|
| `fastcode/retriever.py` | 1,700+ | **Critical** — core retrieval logic |
| `fastcode/agent_tools.py` | ~595 | **High** — security boundary |
| `fastcode/cache.py` | ~736 | Medium |
| `fastcode/indexer.py` | ~566 | High |
| `fastcode/iterative_agent.py` | ~3,963 | Medium (agent logic) |

---

## 4. AST Parsing Assessment

### Language Support

**Excellent coverage** via `tree-sitter-language-pack` (170+ languages) with fallback to individual packages for core languages (Python, JS, TS, Java, Go, C/C++, Rust, C#).

### Robustness

- Language caching prevents redundant loading
- `is_healthy()` validates parser before use
- Graceful fallback chain: language-pack -> individual packages -> skip

### Finding: No Malformed Code Testing

No tests for malformed/partial code files. Tree-sitter is generally robust with partial parses, but this should be verified.

---

## 5. MCP Server Assessment

### Tool Definitions

11 tools properly defined with docstrings and type hints:
- `code_qa` — core Q&A with multi-repo support
- `list_sessions`, `get_session_history`, `delete_session` — session management
- `list_indexed_repos`, `delete_repo_metadata` — index management
- `search_symbol` — find symbols by name across indexed repos
- `get_repo_structure` — high-level repository summary
- `get_file_summary` — file structure (classes, functions, imports)
- `get_call_chain` — trace function/method call chains
- `reindex_repo` — force full re-index of a repository

### Transport Support

- stdio (default) — local development
- streamable-http — recommended for network deployment
- sse — deprecated

### Finding: No MCP Health Check Endpoint

No `/health` or readiness probe on the MCP server itself. Note: `api.py` does have a `GET /health` endpoint, but the MCP server (which runs as a separate process) lacks one for container orchestration.

---

## 6. CI/CD Assessment

### Current Pipeline (GitLab CI)

```
lint (ruff) → test (pytest, 15% coverage) → type-check (mypy) → security (bandit + pip-audit)
```

### Gaps

1. No retrieval quality regression test in CI
2. No MCP server health check
3. Coverage threshold is only 15% — should be raised progressively
4. Python version not pinned (uses `3.12` but many features require `3.11+`)
5. No FAISS index reproducibility verification

---

## 7. Appendix: Files Modified

| File | Change |
|------|--------|
| `fastcode/path_utils.py` | Fixed `is_safe_path()` prefix collision + null byte injection |
| `mcp_server.py` | Added input validation + `FASTCODE_ALLOWED_PATHS` allowlist |
| `tests/test_security.py` | New — 17 security tests |
| `tests/test_monkey.py` | New — 42 monkey/fuzz tests |
