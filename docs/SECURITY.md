# Security model — ebridge-fastcode

> Operational companion to [AUDIT-REPORT.md](../AUDIT-REPORT.md). The audit
> lists **findings**; this doc describes the **surface** an operator has to
> reason about and the **controls** currently in place. Refreshed
> 2026-04-18.

---

## 1. Threat surface

FastCode exposes three network surfaces plus a local CLI:

| Surface | File | Authn | Authz |
|---------|------|-------|-------|
| REST API | `api.py` | Keycloak via `ebridge-shared[auth]` when importable (`_auth_dependencies` attached to every protected route). Falls back to open if the import fails. | n/a (binary: authenticated or not) |
| MCP server | `mcp_server.py` | **None** (tracked in [ROADMAP](../ROADMAP.md)). Local-path indexing gated by `FASTCODE_ALLOWED_PATHS` allowlist. | n/a |
| Streamlit Web UI | `web_app.py` | Inherits whatever fronts it (reverse proxy, SSO) | n/a |
| CLI | `main.py` | OS-level (file permissions) | n/a |

Both the REST API and the MCP server can clone arbitrary Git URLs and index
local directories. **Assume anyone who can reach the MCP port can read any
path that the running user can read unless `FASTCODE_ALLOWED_PATHS` is set.**

---

## 2. Controls in place

### 2.1 Path safety (`fastcode/path_utils.py`)

`PathUtils.is_safe_path()` (line 248) guards every agent-driven file
access. It:

1. **Rejects null bytes** at line 260 — blocks `src/main.py\x00.txt`
   truncation attacks against C-level syscalls.
2. **Resolves the path** via `resolve_path()` (handles repo-name overlap,
   e.g. repo_root ending in `C` and input starting with `C/...`).
3. **Checks containment** via `_is_within_root()` at line 274, using an
   `os.sep`-aware comparison. This is the prefix-collision fix:
   `/tmp/repo_evil` is no longer treated as "inside" `/tmp/repo`.

Related helpers:

- `resolve_repo_target_path()` — resolves ambiguous input (`core` vs
  `django/core`) by consulting the filesystem before stripping.
- `validate_and_normalize_file_pattern()` — same idea for glob patterns.
- `file_path_to_module_path()` uses `os.path.commonpath()` defensively so
  paths on a different drive (Windows) or unrelated prefixes return
  `None` instead of a bogus module name.

Tests: `tests/test_security.py::TestPathTraversal::*`,
`tests/test_monkey.py::TestInjectionPatterns::*`.

### 2.2 MCP allowlist (`mcp_server.py`)

`_is_path_allowed()` at line 179 reads `FASTCODE_ALLOWED_PATHS`
(comma-separated absolute paths) and blocks any `code_qa()` call whose
resolved path isn't inside one of them. Enforced at line 349.

**Deployment requirement**: set this env var. Empty / unset means "allow
everything readable by the process", which is the historical behaviour but
not a safe default for network-exposed MCP.

### 2.3 Input validation (MCP `code_qa()`)

At `mcp_server.py:455`:

- `question` — max **50,000 characters**
- `repos` — max **20**, non-empty
- Empty / whitespace-only question rejected
- `session_id` format — **open** (see [ROADMAP](../ROADMAP.md))

### 2.4 ReDoS mitigation (`fastcode/agent_tools.py`)

- Regex path (`use_regex=True`): `re.compile()` at line 177 is wrapped in
  `try/except re.error` → graceful failure.
- Literal path (`use_regex=False`): input is pre-escaped via `re.escape()`
  at lines 187-190, eliminating injection. The `re.compile()` at line 192
  inherits safety from the escape.
- Glob→regex compile at line 214 takes author-controlled patterns only
  (not user search terms).

This mitigates injection and compilation errors; it **does not** prevent
catastrophic backtracking on pathological patterns. Tracked as SEC-005 in
[AUDIT-REPORT.md](../AUDIT-REPORT.md).

### 2.5 Bandit / pip-audit gating

`.gitlab-ci.yml` runs:

```
bandit -c bandit.yaml -r fastcode/ api.py mcp_server.py main.py web_app.py \
       nanobot/nanobot/agent/tools/shell.py -ll
pip-audit -r requirements.txt --strict --desc
```

`pip-audit --strict` fails the build on any known CVE in a pinned
dependency. Add ignores deliberately, not by default.

---

## 3. Known residual risks

| Ref | Risk | Status |
|-----|------|--------|
| SEC-002 | No MCP authentication. `FASTCODE_ALLOWED_PATHS` only bounds *which paths* can be indexed, not *who* can call the tools. | Keycloak wiring is the next P0 in ROADMAP. |
| SEC-004 | 15 `pickle.load()` sites across `vector_store.py`, `retriever.py`, `cache.py`, `main.py`, `graph_builder.py`. An attacker who writes under `data/vector_store/` or `data/cache/` gets arbitrary code execution. | Mitigated operationally by filesystem permissions; migration plan is JSON for metadata and `safetensors` for vectors. |
| SEC-005 | Regex compilation is safe; pathological patterns can still hang the worker with catastrophic backtracking. | Tracked. Consider regex complexity limit or `re2`. |

---

## 4. Secrets handling

- `.env` is git-ignored (see `.gitignore`) and mounted read-only into the
  FastCode container via `docker-compose.yml`.
- `nanobot_config.json` contains Feishu `appId` / `appSecret` and is
  mounted at `/home/appuser/.nanobot/config.json` inside the Nanobot
  container. Keep its permissions restrictive.
- Environment variables consumed: `OPENAI_API_KEY`, `MODEL`, `BASE_URL`,
  `FAST_MODEL`, `NANOBOT_MODEL`, `EMBEDDING_API_KEY`, `OLLAMA_BASE_URL`,
  `QDRANT_URL`, `FASTCODE_ALLOWED_PATHS`.
- Never commit `*.pkl` files from the `data/` tree — they contain
  executable payloads by construction.

---

## 5. Reporting

Follow the parent e-Bridge workspace security policy. The short version:

- Critical findings: file under the Internal security tracker.
- Non-critical with a fix in hand: reference the SEC-xxx in
  [AUDIT-REPORT.md](../AUDIT-REPORT.md) and add a regression test under
  `tests/test_security.py` or `tests/test_monkey.py`.
