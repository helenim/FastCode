# Tutorials — fastcode

Learning-oriented walkthroughs that take a newcomer from zero to first successful code-intelligence query with FastCode.

## First-run walkthrough

1. From the workspace root, run `git submodule update --init --recursive` and `cd 2d-studio-ebridge-fastcode`.
2. Create a Python 3.11+ virtualenv (or `uv venv --python=3.12`) and activate it.
3. Install canonical dependencies: `pip install -r requirements.txt` (the fork treats `requirements.txt` as the CI source of truth — there is no committed `uv.lock`).
4. Copy `env.example` to `.env` and set `OPENAI_API_KEY`, `MODEL`, and `BASE_URL` for your LLM provider.
5. Launch the Web UI: `python web_app.py --host 0.0.0.0 --port 5777` and open `http://localhost:5777`.
6. Use the sidebar to point FastCode at a repository, let it index (AST parsing + BM25 + graph build), then ask a natural-language question.
7. Optionally launch the REST API in a second terminal: `python api.py --port 8000` and browse OpenAPI docs at `http://localhost:8000/docs`.
8. For IDE integration, add the MCP block from the parent README (`mcp_server.py`, stdio transport) to Cursor or Claude Code.

## Other tutorials planned

- **Index a multi-repo project** — drive `code_qa` with multiple repo paths so cross-repo reasoning and LLM-based repo selection kick in.
- **Switch to a local Ollama backend** — swap `BASE_URL` to `http://localhost:11434/v1` with `qwen3-coder-30b_fastcode` for on-prem use.
- **Ship FastCode as a Docker stack with the Nanobot Feishu bot** — walkthrough of `./run_nanobot.sh` and `docker-compose.yml` (ports 8001 and 18791).
- **Run FastCode behind Keycloak auth** — enable the optional `ebridge_auth` package so REST routes require workspace JWTs.
- **Use FastCode from the CLI for CI impact analysis** — `python main.py query --repos ... --query "What would break if I change the User model?"`.

---
Last updated: 2026-04-18
Back: [submodule hub](../README.md) · [workspace hub](../../../docs/README.md)
