---
name: kg-query
description: Query the ebridge knowledge graph (Neo4j-backed) for entities, relations, archetype context, and Louvain community summaries. Use when the question is about how the platform fits together rather than a single repo's code.
---

# kg-query (2d-studio-ebridge-fastcode)

Use this skill to answer cross-platform questions that span repos, archetypes, or domain entities. The KG holds the platform's ontology, GraphRAG community summaries, archetype registry, and conversation memory.

## When to invoke

- "What archetypes use 2d-studio-ebridge-fastcode?"
- "Which submodules emit `ebridge.economy.*` events?"
- "Summarize the cohort grounding setup."
- Architecture questions answered better by the graph than by reading files.
- Recalling earlier decisions via `recall_memory` / `save_memory`.

## MCP tools available

The `knowledge-graph` MCP server exposes:

| Tool | Purpose |
|---|---|
| `execute_cypher_query` | Raw Cypher on Neo4j (use for precise lookups). |
| `get_entity_neighborhood` | Pull an entity + its neighbors (1–2 hops). |
| `get_graph_statistics` | Counts per label/relationship; sanity check. |
| `query_community_summaries` | Louvain communities + HyPE summaries (GraphRAG). |
| `run_community_summaries` | Refresh community summaries (LLM-backed; gated). |
| `ingest_hype_prompts` | Add hypothetical-embedding prompts. |
| `recall_memory` / `save_memory` / `forget_memory` | User-scoped memory. |
| `search_lorebook` / `get_character_persona` / `sync_character_to_graph` | Character + lorebook. |

## Quick example

```jsonc
{ "tool": "query_community_summaries", "args": { "limit": 5 } }
```

```jsonc
{ "tool": "execute_cypher_query", "args": { "query": "MATCH (a:Archetype)-[:USES]->(r:Repo {name: '2d-studio-ebridge-fastcode'}) RETURN a.name LIMIT 25" } }
```

## Implemented archetypes (from `archetype-registry.yaml`)

When asking the KG about agent behaviour, refer to these by `id` — they're the agent personalities that consume / mutate the platform graph today:

- **Character Engine** (`character-engine`) — domain `ai`, tier 2
- **Commerce Coordinator** (`commerce-coordinator`) — domain `commerce`, tier 2
- **Financial Controller** (`financial-controller`) — domain `finance`, tier 2
- **Inventory Controller** (`inventory-controller`) — domain `commerce`, tier 2
- **Audit Agent** (`audit-agent`) — domain `observability`, tier 3
- **Cognitive Memory** (`cognitive-memory`) — domain `ai`, tier 3
- **Curator** (`curator`) — domain `quality`, tier 3
- **Data Explorer** (`data-explorer`) — domain `data`, tier 3

The full archetype catalogue (incl. planned + deprecated entries) lives in `archetype-registry.yaml` at the workspace root.

## When NOT to invoke

- Pure code-search questions about a single repo (use `fastcode-search`).
- The KG has no data yet for the topic — fall back to reading source.
