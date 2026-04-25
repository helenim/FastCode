# Cross-repository code indexing — reference

How FastCode builds and queries a unified index across multiple repositories.
Closes [DRIFT-2D-005] from
[docs/audits/docs-structure-audit-2026-04-18.md](../../../docs/audits/docs-structure-audit-2026-04-18.md).

## Inputs

The indexer consumes source files matched by `supported_extensions` declared in
[`config/config.yaml`](../../config/config.yaml) — `.py, .js, .ts, .jsx, .tsx,
.java, .go, .cpp, .c, .h, .rs, .rb, .php, .cs, .swift, .kt, .pyx, .toml, .md,
.txt, .yaml, .rst, .json, .html, .css, .xml`. Files larger than
`repository.max_file_size_mb` (default 5 MB) are skipped, and paths matching
`repository.ignore_patterns` (`node_modules`, `__pycache__`, `dist/*`, `*.lock`, …)
never reach the parser. `RepositoryLoader.scan_files()`
([`fastcode/loader.py`](../../fastcode/loader.py)) is the single entry point —
each yielded dict contains `path`, `relative_path`, `extension`, and `size`.

## Per-repository indexing

`FastCode.index_repository()` ([`fastcode/main.py`](../../fastcode/main.py))
runs three pipelines per repo:

1. **AST parsing & element emission.** `CodeIndexer.index_repository(repo_name,
   repo_url)` in [`fastcode/indexer.py`](../../fastcode/indexer.py) produces
   `CodeElement` dataclasses at four levels — `file`, `class`, `function`,
   `documentation`. Each element carries `repo_name` and `repo_url` and an `id`
   built by `_generate_id()` as `{repo_prefix}_{type}_{md5_16}` where
   `repo_prefix = normalize_path(repo_name) or "default"`. The hash input
   includes the repo prefix, so two repos with identically-named symbols
   produce different IDs.
2. **Embeddings + FAISS.** `CodeEmbedder` generates per-element vectors, then
   `FaissVectorStore` (an `IndexHNSWFlat` with `m=16`, `efConstruction=200`,
   `efSearch=50` by default) stores them. Metadata rides alongside the vectors
   in a Python list, with `repo_name` and `repo_url` preserved on every record.
3. **Global maps + graphs.** `GlobalIndexBuilder`
   ([`fastcode/global_index_builder.py`](../../fastcode/global_index_builder.py))
   builds `file_map` (abs path → file_id), `module_map` (dotted module →
   file_id), and `export_map` (module → {symbol_name: node_id}). Then
   `CodeGraphBuilder` ([`fastcode/graph_builder.py`](../../fastcode/graph_builder.py))
   constructs six `networkx` graphs — `call_graph`, `dependency_graph`,
   `inheritance_graph`, `tests_graph`, `co_change_graph`, `type_usage_graph`.

## Cross-repository deduplication

FastCode keeps repos **separable, not merged**. There is no fully-qualified
canonical name (e.g. `repo::module.Symbol`); the repo boundary is enforced two
ways:

- **ID namespacing.** `CodeIndexer._generate_id()` prepends the normalized
  `repo_name` to every element ID — collisions are avoided by hash input, not
  by a post-hoc dedup pass.
- **Repo-aware edge building.** `CodeGraphBuilder._build_dependency_graph()`
  and `_fallback_to_local_inheritance_resolution()` explicitly skip any edge
  whose target element has a different `repo_name` than the source (comments
  mark these as the "Multi-Repo Collision Fix"). Cross-repo imports therefore
  do **not** appear in the dependency graph — a deliberate precision-over-recall
  choice with no override flag.

There is no hash-based content dedup of vectors: if repo A and repo B each
contain an identical `utils.py`, both are embedded and stored independently,
tagged by `repo_name`.

## Query path

`VectorStore.search(query_vector, k, repo_filter=…)` applies the optional
`repo_filter` as a metadata predicate on each candidate before returning
`(metadata, score)` tuples. For hybrid queries, `HybridRetriever` combines
FAISS similarity with a per-repo BM25 index (`save_bm25(repo_name)` in
[`fastcode/retriever.py`](../../fastcode/retriever.py)). Multi-repo QA first
runs `RepositorySelector.select_relevant_files()`
([`fastcode/repo_selector.py`](../../fastcode/repo_selector.py)) — an LLM pass
that scores `repo_overviews` and narrows the downstream search to the top-N
repos before the vector + BM25 merge.

## Storage layout on disk

`vector_store.persist_directory` (default `./data/vector_store`) holds one
FAISS index + one metadata file **per repo**, named after the `repo_name`:

```
data/vector_store/
  {repo_name}.faiss                # HNSW index
  {repo_name}_metadata.jsonl       # Header + one JSON record per vector
  {repo_name}_metadata.pkl.legacy  # Post-migration leftover (see FINDING-EXT-C-004)
  {repo_name}_graphs.pkl           # Pickled networkx graphs
  {repo_name}_bm25.pkl             # BM25Okapi state
  repo_overviews.pkl               # Summary + README per repo (for RepositorySelector)
```

`VectorStore.scan_available_indexes()` walks the directory and lists every
`*.faiss` file as one repo. `merge_from_index(repo_name)` reconstructs vectors
from a sibling FAISS file and adds them to the in-memory store — this is how
multi-repo sessions load many repos into one search surface without rebuilding.

**Pickle migration note.** Metadata was historically pickled; `load_metadata()`
auto-migrates `.pkl` → `.jsonl` on first read and renames the old file to
`.pkl.legacy` (see `_PICKLE_DEPRECATION_MSG` in `vector_store.py`).

## Related

- [docs/MCP.md](../MCP.md) — MCP server configuration
- [ADR-016: FastCode code intelligence](../../../docs/adr/016-fastcode-code-intelligence.md)

---
Last updated: 2026-04-18
Back: [submodule hub](../README.md)
