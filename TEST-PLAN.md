# Test Plan: ebridge-fastcode

> Based on audit findings from 2026-04-07

---

## Current State

- **15 test files** (13 existing + 2 new from audit)
- **5 collectible** without full dependency installation
- **77 tests passing**, 8 failing (missing deps), 1 xfail (known ReDoS)
- **Coverage**: ~15% (estimated — many modules untestable due to import chain)

---

## New Test Files (Created During Audit)

### `tests/test_security.py` — 17 tests

| Test Class | Tests | Status |
|-----------|-------|--------|
| `TestPathTraversal` | 9 | All passing (3 previously failing, now fixed) |
| `TestModulePathContainment` | 3 | All passing |
| `TestMCPInputValidation` | 2 | All passing |
| `TestReDoS` | 2 | 1 passing, 1 xfail (SEC-005) |
| `TestPickleSafety` | 1 | Passing |

### `tests/test_monkey.py` — 42 tests

| Test Class | Tests | Status |
|-----------|-------|--------|
| `TestEmptyInputs` | 7 | 4 passing, 3 skipped (faiss) |
| `TestOversizedInputs` | 4 | 2 passing, 2 skipped (faiss) |
| `TestUnicodeEdgeCases` | 6 | All passing |
| `TestInjectionPatterns` | 17 | 13 passing, 4 skipped (faiss) |
| `TestConcurrentAccess` | 2 | 1 passing, 1 skipped (faiss) |
| `TestVectorStoreEdgeCases` | 6 | All skipped (faiss) |

---

## Proposed New Test Files

### 1. `tests/test_path_utils.py` — Path Security Deep Dive

**Priority**: P0
**Why**: `is_safe_path()` is the security boundary. Need comprehensive coverage beyond what `test_security.py` provides.

Tests to add:
- Symlink resolution vs joined path behavior
- Windows-style paths on Unix (`C:\Users\...`)
- URL-encoded path components (`%2e%2e` = `..`)
- `resolve_path()` overlap detection edge cases
- `normalize_path_with_repo()` with duplicate repo names

### 2. `tests/test_retriever_unit.py` — Retrieval Logic

**Priority**: P1
**Why**: Core retrieval has zero test coverage. All 1,700+ lines untested.

Tests to add:
- RRF fusion with known scores — verify formula correctness
- Weighted linear fusion — verify weight application
- BM25 tokenization output for code-specific strings
- Score normalization edge cases (all-zero scores, single result)
- Diversity penalty calculation
- Type-weight reranking multipliers
- Repo filter enforcement

### 3. `tests/test_agent_tools.py` — Agent Tool Security

**Priority**: P1
**Why**: Tools accept user paths and regex patterns — security-critical.

Tests to add:
- `list_directory()` with traversal attempts
- `search_codebase()` with ReDoS patterns
- `read_file_content()` with binary files, encoding errors
- `get_file_info()` with symlinks
- Recursive directory filtering (`.git`, `node_modules` excluded)

### 4. `tests/test_cache.py` — Cache Correctness

**Priority**: P2
**Why**: Cache uses pickle, has TTL logic, and can serve stale results.

Tests to add:
- TTL expiration
- Cache key collisions
- Concurrent cache reads/writes
- Corrupt cache file recovery
- Cache size limits

### 5. `tests/test_retrieval_quality.py` — Regression Benchmarks

**Priority**: P1
**Why**: No way to detect retrieval quality regression.

Tests to add:
- Create synthetic Python repo (3-5 files with known functions)
- Index with local SentenceTransformer
- Query: "function that calculates fibonacci" → assert correct file in top-3
- Query: exact function name → assert top-1 match
- Query: semantic concept → assert relevant files in top-5
- Run as part of CI (no external API needed)

### 6. `tests/test_mcp_integration.py` — MCP Tool End-to-End

**Priority**: P2
**Why**: Existing MCP tests only test helpers, not actual tool execution.

Tests to add:
- `code_qa()` with mocked FastCode — verify output format
- `list_sessions()` empty state
- `delete_session()` nonexistent session
- Input validation rejections (empty repos, oversized question)
- `FASTCODE_ALLOWED_PATHS` enforcement

---

## Testing Infrastructure Improvements

### Fix `__init__.py` Import Chain

**Problem**: `fastcode/__init__.py` eagerly imports `AnswerGenerator` which requires `anthropic`. Any test importing `fastcode.*` fails without full deps.

**Solution**: Use lazy imports via `__getattr__`:
```python
def __getattr__(name):
    if name == "AnswerGenerator":
        from .answer_generator import AnswerGenerator
        return AnswerGenerator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

### Add Missing Dev Dependencies

- `httpx` — required by `test_api.py` (FastAPI TestClient)
- `anthropic` — required by 10 test files via import chain

### Progressive Coverage Targets

| Milestone | Target | Timeline |
|-----------|--------|----------|
| Current | ~15% | Now |
| After import fix | 30% | Sprint 1 |
| After new test files | 50% | Sprint 2 |
| Mature | 70% | Quarter end |
