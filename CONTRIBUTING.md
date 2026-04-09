# Contributing to e-Bridge FastCode

Thank you for your interest in contributing. This document explains how to get set up, run checks, and submit changes.

## Development setup

1. **Clone the repository**

   ```bash
   git clone https://github.com/helenim/2d-studio-ebridge-fastcode.git
   cd 2d-studio-ebridge-fastcode
   ```

2. **Install dependencies**

   This module uses **pip** (not uv):

   ```bash
   pip install -e .
   pip install -e ".[dev]"
   ```

## Code style and quality

- **Linting:** [Ruff](https://docs.astral.sh/ruff/).
- **Type checking:** [mypy](https://mypy-lang.org/).

```bash
ruff check .
ruff format --check .
pytest tests/ -v
```

## Testing

```bash
pytest tests/ -v
pytest tests/ -v --cov=fastcode
```

## Running locally

```bash
# Web UI
python web_app.py --port 5777

# REST API
python api.py --port 8000

# MCP server (stdio)
python mcp_server.py
```

## Commit conventions

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(search): add cross-repo symbol resolution
fix(ast): handle Python 3.12 match statement
test(mcp): add code_qa multi-turn test
```
