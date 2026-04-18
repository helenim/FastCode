# CI/CD Recommendations: ebridge-fastcode

> Based on audit findings from 2026-04-07, refreshed 2026-04-18

---

## Current Pipeline

**GitLab CI (`.gitlab-ci.yml`)**

```
lint
  ├── ruff (fastcode/, api.py, mcp_server.py, main.py, web_app.py)
  │    + ruff --select F,B,S on nanobot/nanobot/
  └── whatsapp-bridge (cd nanobot/bridge && npm ci && npm run build
                       && npm audit --audit-level=high)
test
  ├── pytest (coverage 15% on fastcode + api + mcp_server)
  └── nanobot-pytest  (pip install -e ./nanobot[dev])
type-check
  └── mypy (strict on entrypoints, ignore_errors=True inside fastcode/*)
security
  └── bandit -c bandit.yaml  +  pip-audit --strict
```

**GitHub Actions (`.github/workflows/ci.yml`)**

```
lint (ruff)  →  test (pytest, --cov-fail-under=50 on api + mcp_server only)
```

> The GitHub Actions coverage gate is narrower than GitLab's: it excludes
> `fastcode/` and only rides on the two entrypoints, which is what allows it
> to demand 50% while the library-wide GitLab gate stays at 15%.

---

## Recommendations

### 1. Fix Test Collection (P0 — still open)

**Problem**: `fastcode/__init__.py` eagerly imports `AnswerGenerator`,
`IterativeAgent` and friends. Every test that touches `from fastcode import X`
drags in `anthropic` at collection time, which keeps ~14 of the 19 test files
uncollectable without a full dependency install. Local runs on a slim env
therefore execute ~35 of potentially 200+ tests.

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
2. ~~Add `httpx` to dev deps~~ (already in `requirements.txt` and `pyproject.toml[dev]`)
3. ~~Pin `requires-python = ">=3.11"` in `pyproject.toml`~~ (already set)
4. ~~Add the new `test_security.py` and `test_monkey.py` to CI~~ (done — both run under the `pytest` GitLab job and the GitHub Actions `test` job)
5. ~~Add `whatsapp-bridge` lint job~~ (already present in `.gitlab-ci.yml`; runs `npm ci`, `npm run build`, and `npm audit --audit-level=high` inside `nanobot/bridge/`)
6. ~~Add `nanobot-pytest` job~~ (present; installs `./nanobot[dev]` and runs its pytest suite)
