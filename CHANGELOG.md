# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- AST-based code indexing for 8+ languages (Python, JS/TS, Java, Go, C/C++, Rust, C#)
- Hybrid search engine (semantic embeddings + BM25 keyword search)
- Multi-layer code graphs (call, dependency, inheritance)
- Multi-turn code QA with session management
- Three entry points: Streamlit Web UI, REST API, MCP server
- MCP tools (code_qa, search_symbol, get_repo_structure, get_call_chain, etc.)
- Nanobot + Feishu/Lark bot integration
- Budget-aware query decision making
- REST API with repository management, streaming queries, and caching
