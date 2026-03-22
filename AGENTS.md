# FastCode submodule — agent notes

This repo is often consumed as **`2d-studio-ebridge-fastcode`** inside the e-Bridge workspace. Prefer the parent [README.md](../README.md) and [AGENTS.md](../AGENTS.md) for clone/submodule setup and platform-wide rules.

## Quick facts

- **Canonical Python deps:** `requirements.txt` (used in CI). `uv` is optional; no `uv.lock` here.
- **Ports:** See [README.md](README.md) section *Default ports* — web UI defaults to **5777**, REST API **8000** locally / **8001** in Docker.
- **Compose:** Only trust [`docker-compose.yml`](docker-compose.yml) for stack layout.
- **REST docs:** Run `api.py`, then `/docs` (OpenAPI). Checked-in summary: [`docs/API.md`](docs/API.md).
