"""Tests for Phase 5: Graph schema expansion (tests, co-change, type usage graphs)."""


from fastcode.graph_builder import CodeGraphBuilder
from fastcode.indexer import CodeElement


def _make_element(id, name, type="function", file_path="a.py", metadata=None):
    return CodeElement(
        id=id,
        name=name,
        type=type,
        file_path=file_path,
        relative_path=file_path,
        language="python",
        start_line=1,
        end_line=10,
        code="pass",
        signature=(metadata or {}).get("signature"),
        docstring=None,
        summary=None,
        metadata=metadata or {},
    )


def _make_config(**graph_overrides):
    cfg = {
        "graph": {
            "build_call_graph": False,
            "build_dependency_graph": False,
            "build_inheritance_graph": False,
            "build_tests_graph": True,
            "build_co_change_graph": False,
            "build_type_usage_graph": True,
            **graph_overrides,
        },
        "vector_store": {"persist_directory": "/tmp/test_graphs"},
    }
    return cfg


class TestTestsGraph:
    def test_naming_convention_test_prefix(self):
        """test_foo should link to foo via TESTS edge."""
        builder = CodeGraphBuilder(_make_config())
        elements = [
            _make_element("f1", "foo", type="function"),
            _make_element("t1", "test_foo", type="function", file_path="tests/test_a.py"),
        ]
        builder.build_graphs(elements)

        assert builder.tests_graph.has_edge("t1", "f1")

    def test_naming_convention_test_class(self):
        """TestFoo should link to Foo via TESTS edge."""
        builder = CodeGraphBuilder(_make_config())
        elements = [
            _make_element("c1", "Foo", type="class"),
            _make_element("tc1", "TestFoo", type="class", file_path="tests/test_foo.py"),
        ]
        builder.build_graphs(elements)

        assert builder.tests_graph.has_edge("tc1", "c1")

    def test_no_false_positives(self):
        """Non-test functions should not appear in tests graph."""
        builder = CodeGraphBuilder(_make_config())
        elements = [
            _make_element("f1", "foo", type="function"),
            _make_element("f2", "bar", type="function"),
        ]
        builder.build_graphs(elements)

        assert builder.tests_graph.number_of_edges() == 0

    def test_import_based_matching(self):
        """Test functions importing specific targets should link to them."""
        builder = CodeGraphBuilder(_make_config())
        builder.imports_by_file = {
            "tests/test_util.py": [
                {"module": "mylib.util", "names": ["process_data"]}
            ]
        }
        elements = [
            _make_element("f1", "process_data", type="function", file_path="mylib/util.py"),
            _make_element("t1", "test_integration", type="function", file_path="tests/test_util.py"),
        ]
        builder.build_graphs(elements)

        assert builder.tests_graph.has_edge("t1", "f1")


class TestTypeUsageGraph:
    def test_function_references_class(self):
        """Function with type annotation referencing a class should create USES_TYPE edge."""
        builder = CodeGraphBuilder(_make_config())
        elements = [
            _make_element("c1", "UserService", type="class"),
            _make_element(
                "f1", "get_users", type="function",
                metadata={"signature": "def get_users(svc: UserService) -> list[User]"},
            ),
        ]
        builder.build_graphs(elements)

        assert builder.type_usage_graph.has_edge("f1", "c1")

    def test_no_edge_for_unknown_types(self):
        """Types not defined in the codebase should not create edges."""
        builder = CodeGraphBuilder(_make_config())
        elements = [
            _make_element(
                "f1", "process", type="function",
                metadata={"signature": "def process(x: int) -> str"},
            ),
        ]
        builder.build_graphs(elements)

        assert builder.type_usage_graph.number_of_edges() == 0

    def test_multiple_type_references(self):
        """Function referencing multiple types should create edges to all of them."""
        builder = CodeGraphBuilder(_make_config())
        elements = [
            _make_element("c1", "Request", type="class"),
            _make_element("c2", "Response", type="class"),
            _make_element(
                "f1", "handle", type="function",
                metadata={"signature": "def handle(req: Request) -> Response"},
            ),
        ]
        builder.build_graphs(elements)

        assert builder.type_usage_graph.has_edge("f1", "c1")
        assert builder.type_usage_graph.has_edge("f1", "c2")


class TestGetRelatedWithNewGraphs:
    def test_related_includes_test_targets(self):
        """get_related_elements should traverse TESTS edges."""
        builder = CodeGraphBuilder(_make_config())
        elements = [
            _make_element("f1", "foo", type="function"),
            _make_element("t1", "test_foo", type="function", file_path="tests/test.py"),
        ]
        builder.build_graphs(elements)

        related = builder.get_related_elements("f1", max_hops=1)
        assert "t1" in related

    def test_related_includes_type_users(self):
        """get_related_elements should traverse USES_TYPE edges."""
        builder = CodeGraphBuilder(_make_config())
        elements = [
            _make_element("c1", "Config", type="class"),
            _make_element(
                "f1", "load_config", type="function",
                metadata={"signature": "def load_config() -> Config"},
            ),
        ]
        builder.build_graphs(elements)

        related = builder.get_related_elements("c1", max_hops=1)
        assert "f1" in related


class TestGraphStats:
    def test_stats_include_new_graphs(self):
        builder = CodeGraphBuilder(_make_config())
        elements = [
            _make_element("f1", "foo"),
            _make_element("t1", "test_foo", file_path="tests/test.py"),
        ]
        builder.build_graphs(elements)

        stats = builder.get_graph_stats()
        assert "tests" in stats
        assert "co_change" in stats
        assert "type_usage" in stats
