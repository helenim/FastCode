# Explanation — fastcode

Understanding-oriented material: why FastCode looks the way it does.

## Key design decisions

- **Three entry points served by one core** — `web_app.py` (Streamlit, 5777), `api.py` (FastAPI, 8000/8001), and `mcp_server.py` (stdio) all share the same AST-indexed library but target different audiences (humans, automation, IDEs). The CLAUDE.md rules forbid merging them.
- **AST parsing is the foundation** — code understanding flows through tree-sitter hierarchical units (files, classes, functions, docs). Bypassing the parser is explicitly prohibited because the hybrid BM25 + semantic + graph index depends on it.
- **Scouting-first navigation** — rather than loading files repeatedly, FastCode builds a semantic map, walks call / dependency / inheritance graphs up to two hops, and only then reads targeted excerpts. This is where the 10× token savings come from.
- **Budget-aware decision making** — the query engine gates work on confidence, query complexity, codebase size, cost, and iteration count. The CLAUDE.md rules explicitly forbid removing this gate because it prevents runaway token spend on very large repos.
- **setuptools + `requirements.txt` (not uv)** — the fork keeps the upstream packaging choice so CI and editable installs behave identically to HKUDS/FastCode; `uv` is only an optional speedup for local installs.

## Related workspace ADRs

- [ADR-016: FastCode code intelligence architecture](../../../docs/adr/016-fastcode-code-intelligence.md) — justifies adopting FastCode as the workspace code-intelligence MCP and pins the integration surface.
- [ADR-006: Model Context Protocol (MCP) for Agent Tooling](../../../docs/adr/006-mcp-integration.md) — frames `code_qa` and the nine supporting MCP tools as first-class agent capabilities.
- [ADR-041: MCP SSE transport](../../../docs/adr/) — rationale for running `mcp_server.py --transport sse` when agents are remote rather than co-located with the IDE.

## Related explanation elsewhere

- [../README.md](../README.md) § "How It Works", "Why FastCode?", and the Semantic-Structural / Cost-Efficient Context Management sections.
- [../CLAUDE.md](../CLAUDE.md) § "Critical Architecture Rules" — three entry points, build system, AST invariants, budget gating.
- [docs/ARCHITECTURE.md](../ARCHITECTURE.md) — deeper component diagrams and data flow.
- [docs/SECURITY.md](../SECURITY.md) and [AUDIT-REPORT.md](../../AUDIT-REPORT.md) — threat model and review findings.

---
Last updated: 2026-04-18
Back: [submodule hub](../README.md) · [workspace hub](../../../docs/README.md)
