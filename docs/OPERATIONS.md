# Operations — ebridge-fastcode

> Deployment, ports, environment, and runbook notes. Refreshed 2026-04-18
> against `Dockerfile`, `docker-compose.yml`, `run_nanobot.sh`, and
> `.gitlab-ci.yml`.

---

## 1. Ports (canonical)

| Service | CLI default | Docker / Compose | Notes |
|---------|-------------|------------------|-------|
| Web UI (`web_app.py`) | **5777** | not published | Streamlit; operator exposes via reverse proxy if needed |
| REST API (`api.py`) | **8000** | **8001** (host → container) | Auth via `ebridge-shared[auth]` when importable |
| MCP server (`mcp_server.py`) | stdio (no port) | n/a | `--port 8080` for `sse` / `streamable-http` |
| Nanobot gateway | — | **18791 → 18790** | Feishu WebSocket and WhatsApp bridge traffic |
| Qdrant (optional) | — | **6333** (external) | `config.yaml: vector_store.qdrant.url` |

Override any port with `--port` on the CLI or with compose `ports:` stanzas.

---

## 2. Environment variables

Loaded from `.env` (FastCode container) or the operator's shell. See
[MCP.md §3](MCP.md#3-environment-variables) for the full MCP table.

Minimum for a working stack:

```
OPENAI_API_KEY=sk-…
MODEL=gpt-5.2                      # strong model
BASE_URL=https://api.openai.com/v1 # OpenAI / OpenRouter / Ollama compatible
# Optional:
FAST_MODEL=gemini-3-flash          # tiered routing; requires config.yaml flag
NANOBOT_MODEL=minimax/minimax-m2.1 # agent reasoning inside Nanobot
EMBEDDING_API_KEY=…                # if embedding.provider = api
QDRANT_URL=http://qdrant:6333      # if vector_store.type = qdrant
FASTCODE_ALLOWED_PATHS=/srv/repos  # MCP safety allowlist
```

`docker-compose.yml` mounts `./.env` read-only at `/app/.env` in the
FastCode container and sets `FASTCODE_API_URL=http://fastcode:8001` in the
Nanobot container.

---

## 3. First-run checklist

1. `git submodule update --init --recursive` (if cloning via the e-Bridge
   workspace).
2. `pip install -r requirements.txt` — this is the canonical dep set; the
   `pyproject.toml[dev]` extras add pytest, pytest-asyncio, pytest-cov,
   httpx.
3. `cp env.example .env` and fill in at least `OPENAI_API_KEY`, `MODEL`,
   `BASE_URL`.
4. Optionally edit `config/config.yaml` (embedding provider, vector store
   backend, retrieval thresholds).
5. Start one of the three entrypoints:
   - `python web_app.py --port 5777`
   - `python api.py --port 8000`
   - `python mcp_server.py` (stdio) or `--transport streamable-http --port 8080`

---

## 4. Docker / compose

The source-of-truth compose file is
[`../docker-compose.yml`](../docker-compose.yml). Key observations:

- `fastcode` service builds from the repo root `Dockerfile`, publishes
  `8001:8001`, and mounts `./.env`, `./config` (read-only), `./data`,
  `./repos`, and `./logs`.
- `nanobot` service builds from `./nanobot/`, publishes `18791:18790`,
  runs as the non-root user `appuser`, mounts
  `./nanobot_config.json → /home/appuser/.nanobot/config.json` (read-only),
  and has `./repos` read-only so it can reference already-cloned sources.
- Named volumes `nanobot-workspace` and `nanobot-sessions` persist
  Nanobot state across restarts.

The Web UI port (5777) is intentionally **not** exposed in the compose
file. Publish it yourself with `ports:` if you need it.

---

## 5. `run_nanobot.sh`

All Nanobot lifecycle flows through `run_nanobot.sh`:

| Command | Effect |
|---------|--------|
| `./run_nanobot.sh` | Smart launch: detects running/stopped/missing-image state |
| `./run_nanobot.sh --build` | Force rebuild images |
| `./run_nanobot.sh --fg` | Foreground with live logs |
| `./run_nanobot.sh stop` | `docker compose stop` |
| `./run_nanobot.sh restart` | `stop` + smart launch |
| `./run_nanobot.sh logs` | `docker compose logs -f` |
| `./run_nanobot.sh status` | Service status + `GET /health` check |
| `./run_nanobot.sh config` | Re-check / regenerate `nanobot_config.json` |
| `./run_nanobot.sh clean` | Stop + remove containers and images |

Run it from Git Bash / WSL on Windows — the script assumes LF endings
(enforced via `.gitattributes`).

---

## 6. WhatsApp bridge (`nanobot/bridge/`)

A Node.js gateway (`nanobot-whatsapp-bridge`) built on the Baileys library.
It lets the same Nanobot instance listen on Feishu *and* WhatsApp.

- Lint + build in CI: `whatsapp-bridge` job in `.gitlab-ci.yml`
  (`npm ci && npm run build && npm audit --audit-level=high`).
- Configuration lives alongside Feishu credentials in
  `nanobot_config.json`; see [README.md](../README.md) for the structure.

---

## 7. Observability

- **Logs**: `./logs/fastcode.log` (rotating; path in `config.yaml:
  logging.file`). Level defaults to `INFO`.
- **Health probe**: `GET /health` on the REST API. The MCP server
  **does not** yet expose one — see [MCP.md §5](MCP.md#5-known-limitations).
- **Bandit artefact**: `bandit-report.json` retained 30 days from the
  `security` GitLab job.

---

## 8. Data lifecycle

On-disk artefacts live under `./data/` and `./repos/`:

- `./data/vector_store/` — FAISS indexes and pickled metadata (see
  [SECURITY.md §3 / SEC-004](SECURITY.md#3-known-residual-risks)).
- `./data/cache/` — query + embedding cache. TTL in
  `config.yaml: cache.ttl` (1 hour) and `cache.dialogue_ttl` (30 days).
- `./repos/<name>` — working copies of indexed repositories.
- `./repo_backup/<name>` — safety copies created before overwrite.

Clearing caches: `POST /clear-cache` (REST) or delete the directories while
the service is stopped. Never hot-edit pickle files.

---

## 9. Upgrade / rollback

Because `pyproject.toml` version is pinned at `0.0.0` (see
[CHANGELOG.md](../CHANGELOG.md)), upgrades are driven by the **submodule
pointer** in the parent e-Bridge workspace. Typical flow:

1. `git -C 2d-studio-ebridge-fastcode fetch && git -C … checkout <ref>`
2. Run CI in the parent workspace.
3. Rebuild the Docker images (`./run_nanobot.sh --build` or
   `docker compose build`).
4. `docker compose up -d`.

Rollback is the inverse: reset the submodule pointer and rebuild. Pickled
indexes are forward-compatible within the 2.x runtime line; clear `data/`
if the schema of a `*_metadata.pkl` changed (grep `test_metadata_migration.py`
for expected migrations).

---

## 10. Related docs

- [ARCHITECTURE.md](ARCHITECTURE.md) — layout + request flow.
- [MCP.md](MCP.md) — MCP server reference.
- [SECURITY.md](SECURITY.md) — threat surface and controls.
- [../CICD-RECOMMENDATIONS.md](../CICD-RECOMMENDATIONS.md) — pipeline detail.
