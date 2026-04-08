# CI/CD Recommendations: ebridge-fastcode

> Based on audit findings from 2026-04-07

---

## Current Pipeline

```
GitLab CI:  lint (ruff) → test (pytest, 15%) → type-check (mypy) → security (bandit + pip-audit)
GitHub Actions: lint (ruff) → test (pytest, 50%)
```

---

## Recommendations

### 1. Fix Test Collection (P0)

**Problem**: 10 of 13 test files fail to collect because `fastcode/__init__.py` eagerly imports `AnswerGenerator` → `anthropic`. This means CI only runs ~35 of potentially 200+ tests.

**Fix**: Refactor `fastcode/__init__.py` to use lazy imports:
```python
_LAZY_IMPORTS = {
    "AnswerGenerator": ".answer_generator",
    "IterativeAgent": ".iterative_agent",
    # ...
}

def __getattr__(name):
    if name in _LAZY_IMPORTS:
        mod = importlib.import_module(_LAZY_IMPORTS[name], __name__)
        return getattr(mod, name)
    raise AttributeError(name)
```

**Impact**: Unblocks all 13 test files, raises effective coverage from ~15% to 30%+.

### 2. Raise Coverage Thresholds Progressively (P1)

**Current**: 15% (GitLab), 50% (GitHub Actions — only covers `api` and `mcp_server`)

**Proposed schedule**:

| Month | GitLab | GitHub Actions |
|-------|--------|----------------|
| April 2026 | 15% → 25% | 50% (keep) |
| May 2026 | 25% → 35% | 50% → 55% |
| June 2026 | 35% → 50% | 55% → 65% |

**Implementation**: Update `--cov-fail-under` in `.gitlab-ci.yml` and `.github/workflows/ci.yml`.

### 3. Add Retrieval Quality Regression Test (P1)

**Purpose**: Detect when retrieval quality degrades after code changes.

**Implementation**: Add a new CI job:
```yaml
retrieval-regression:
  stage: test
  before_script:
    - pip install pytest -r requirements.txt
  script:
    - python -m pytest tests/test_retrieval_quality.py -v --tb=short
  allow_failure: false
```

**Test**: Create a small synthetic Python repo (3-5 files), index with local SentenceTransformer, query with known questions, assert correct files in top-k. No external API needed.

### 4. Add MCP Server Health Check (P1)

**Purpose**: Verify MCP server starts and responds before deployment.

**Implementation**: Add to GitLab CI:
```yaml
mcp-health:
  stage: test
  script:
    - timeout 30 python mcp_server.py --transport streamable-http --port 9090 &
    - sleep 5
    - curl -sf http://localhost:9090/mcp || exit 1
    - kill %1
```

**Alternative**: Add a `GET /health` endpoint to `mcp_server.py` returning `{"status": "ok", "version": "2.0.0"}`.

### 5. Pin Python Version (P1)

**Problem**: GitLab CI uses `PYTHON_VERSION: "3.12"` but the codebase requires `>=3.11`. GitHub Actions tests on `3.11` and `3.12`. Locally, Python 3.9 is common on macOS.

**Fix**: Add to `pyproject.toml`:
```toml
[project]
requires-python = ">=3.11"
```

Add explicit version check in CI:
```yaml
variables:
  PYTHON_VERSION: "3.12"
```

### 6. Add SAST Beyond Bandit (P2)

**Current**: Bandit scans for Python security issues + pip-audit for known CVEs.

**Additions**:
- **Semgrep** — Better pattern matching for security issues, lower false-positive rate than Bandit
- **Safety** — Complementary to pip-audit for vulnerability scanning
- **Trivy** — Container image scanning (if Docker images are published)

```yaml
semgrep:
  stage: security
  image: returntocorp/semgrep
  script:
    - semgrep --config auto fastcode/ mcp_server.py api.py
  allow_failure: true  # start permissive, tighten over time
```

### 7. Add Hypothesis Property-Based Testing (P2)

**Purpose**: Automatically discover edge cases in path handling and retrieval.

**Add to dev dependencies**:
```toml
[project.optional-dependencies]
dev = ["hypothesis>=6.0"]
```

**Example test**:
```python
from hypothesis import given, strategies as st

@given(st.text())
def test_is_safe_path_never_crashes(path_utils, path):
    result = path_utils.is_safe_path(path)
    assert isinstance(result, bool)
```

### 8. FAISS Index Reproducibility Check (P3)

**Purpose**: Verify that re-indexing the same repo produces identical results.

**Implementation**: 
1. Index a small test repo twice
2. Compare FAISS index checksums
3. Compare metadata pickle checksums

**Note**: HNSW construction is non-deterministic by default. Either:
- Use `Flat` index for reproducibility tests
- Accept approximate equality (top-k results should be identical even if index differs)

---

## Proposed Pipeline (Target State)

```
lint (ruff + semgrep)
  → test (pytest, 50%+ coverage)
  → retrieval-regression (synthetic repo benchmark)
  → mcp-health (server startup check)
  → type-check (mypy)
  → security (bandit + pip-audit + safety)
```

---

## Quick Wins (Can Ship This Week)

1. Raise GitLab coverage from 15% → 25%
2. Add `httpx` to dev deps (unblocks `test_api.py`)
3. Pin `requires-python = ">=3.11"` in `pyproject.toml`
4. Add the new `test_security.py` and `test_monkey.py` to CI (already done)
