"""Tests for Phase 11: Graph-Enhanced RAG — community detection and blast radius."""

import pytest

from fastcode.graph_builder import CodeGraphBuilder
from fastcode.indexer import CodeElement


def _elem(id, name, type="function", file_path="a.py"):
    return CodeElement(
        id=id, name=name, type=type, file_path=file_path,
        relative_path=file_path, language="python",
        start_line=1, end_line=10, code="pass",
        signature=None, docstring=None, summary=None,
        metadata={},
    )


def _make_config(**overrides):
    return {
        "graph": {
            "build_call_graph": True,
            "build_dependency_graph": False,
            "build_inheritance_graph": False,
            "build_tests_graph": False,
            "build_co_change_graph": False,
            "build_type_usage_graph": False,
            "community_detection": True,
            "blast_radius_hops": 2,
            **overrides,
        },
        "vector_store": {"persist_directory": "/tmp/test_ger"},
    }


class TestCommunityDetection:
    def test_detects_communities_in_connected_components(self):
        """Two separate clusters should be detected as different communities."""
        builder = CodeGraphBuilder(_make_config())

        # Cluster 1: a->b->c
        builder.call_graph.add_edge("a", "b")
        builder.call_graph.add_edge("b", "c")

        # Cluster 2: x->y->z
        builder.call_graph.add_edge("x", "y")
        builder.call_graph.add_edge("y", "z")

        communities = builder.detect_communities()
        assert len(communities) == 6  # All nodes assigned

        # Nodes in same cluster should have same community
        assert communities["a"] == communities["b"] == communities["c"]
        assert communities["x"] == communities["y"] == communities["z"]

        # Different clusters should have different communities
        assert communities["a"] != communities["x"]

    def test_community_hubs(self):
        """Hub should be the highest-degree node in each community."""
        builder = CodeGraphBuilder(_make_config())

        # Star graph centered on "hub"
        for i in range(5):
            builder.call_graph.add_edge("hub", f"leaf{i}")

        builder.detect_communities()
        # All nodes in one community, hub should be the hub
        assert builder.get_community_hub("leaf0") == "hub"

    def test_get_community_members(self):
        builder = CodeGraphBuilder(_make_config())
        builder.call_graph.add_edge("a", "b")
        builder.call_graph.add_edge("b", "c")
        builder.detect_communities()

        members = builder.get_community_members("a")
        assert set(members) == {"a", "b", "c"}

    def test_community_for_unknown_node(self):
        builder = CodeGraphBuilder(_make_config())
        assert builder.get_community_members("nonexistent") == []
        assert builder.get_community_hub("nonexistent") is None

    def test_too_few_nodes_skipped(self):
        builder = CodeGraphBuilder(_make_config())
        builder.call_graph.add_edge("a", "b")
        communities = builder.detect_communities()
        assert communities == {}  # < 3 nodes

    def test_disabled_community_detection(self):
        builder = CodeGraphBuilder(_make_config(community_detection=False))
        builder.call_graph.add_edge("a", "b")
        builder.call_graph.add_edge("b", "c")
        builder.call_graph.add_edge("c", "d")
        communities = builder.detect_communities()
        assert communities == {}


class TestBlastRadius:
    def test_direct_callers_have_high_impact(self):
        """Nodes 1 hop away should have high impact scores."""
        builder = CodeGraphBuilder(_make_config())
        builder.call_graph.add_edge("caller", "target")
        builder.call_graph.add_edge("target", "callee")

        radius = builder.blast_radius("target", max_hops=2)
        assert "caller" in radius
        assert "callee" in radius
        # Direct connections have score = weight * 1/(1+1) = 0.5
        assert radius["caller"] > 0.3

    def test_distant_nodes_have_lower_impact(self):
        """Nodes 2 hops away should have lower scores than 1-hop nodes."""
        builder = CodeGraphBuilder(_make_config())
        builder.call_graph.add_edge("a", "b")
        builder.call_graph.add_edge("b", "c")
        builder.call_graph.add_edge("c", "d")

        radius = builder.blast_radius("b", max_hops=2)
        # "a" and "c" are 1 hop, "d" is 2 hops
        if "a" in radius and "d" in radius:
            assert radius["a"] >= radius["d"]

    def test_unreachable_nodes_excluded(self):
        builder = CodeGraphBuilder(_make_config())
        builder.call_graph.add_edge("a", "b")
        builder.call_graph.add_edge("x", "y")  # Disconnected

        radius = builder.blast_radius("a", max_hops=2)
        assert "x" not in radius
        assert "y" not in radius

    def test_self_excluded(self):
        builder = CodeGraphBuilder(_make_config())
        builder.call_graph.add_edge("a", "b")

        radius = builder.blast_radius("a", max_hops=2)
        assert "a" not in radius

    def test_empty_graph(self):
        builder = CodeGraphBuilder(_make_config())
        radius = builder.blast_radius("nonexistent", max_hops=2)
        assert radius == {}

    def test_multi_graph_traversal(self):
        """Blast radius should traverse all graph types."""
        builder = CodeGraphBuilder(_make_config(
            build_tests_graph=True, build_type_usage_graph=True,
        ))
        builder.call_graph.add_edge("func", "callee")
        builder.tests_graph.add_edge("test_func", "func")
        builder.type_usage_graph.add_edge("func", "MyType")

        radius = builder.blast_radius("func", max_hops=1)
        assert "callee" in radius
        assert "test_func" in radius
        assert "MyType" in radius

    def test_respects_max_hops(self):
        builder = CodeGraphBuilder(_make_config())
        builder.call_graph.add_edge("a", "b")
        builder.call_graph.add_edge("b", "c")
        builder.call_graph.add_edge("c", "d")

        radius_1 = builder.blast_radius("a", max_hops=1)
        radius_3 = builder.blast_radius("a", max_hops=3)

        # 1-hop should not include "c" or "d"
        assert "d" not in radius_1
        # 3-hop should include "d"
        assert "d" in radius_3
