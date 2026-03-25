"""Tests for the evaluation pipeline — metrics, golden datasets, and runner."""

import json
from pathlib import Path

import pytest

from evaluation.golden_dataset import GoldenDataset, GoldenQuery
from evaluation.metrics import (
    compute_context_precision,
    compute_mrr,
    compute_ndcg,
    compute_precision_at_k,
    compute_recall_at_k,
)
from evaluation.runner import EvaluationRunner

# -- Fixtures --

RELEVANT = [
    {"file_path": "a.py", "name": "foo"},
    {"file_path": "b.py", "name": "bar"},
    {"file_path": "c.py", "name": "baz"},
]


def _make_retrieved(*names: str) -> list[dict]:
    """Helper: create retrieved elements with given names from known files."""
    mapping = {
        "foo": {"file_path": "a.py", "name": "foo"},
        "bar": {"file_path": "b.py", "name": "bar"},
        "baz": {"file_path": "c.py", "name": "baz"},
        "qux": {"file_path": "d.py", "name": "qux"},
        "quux": {"file_path": "e.py", "name": "quux"},
    }
    return [mapping[n] for n in names]


# -- Metric tests --


class TestNDCG:
    def test_perfect_ranking(self):
        retrieved = _make_retrieved("foo", "bar", "baz")
        assert compute_ndcg(retrieved, RELEVANT, k=3) == pytest.approx(1.0)

    def test_reversed_ranking(self):
        retrieved = _make_retrieved("baz", "bar", "foo")
        # All relevant, just different order — still perfect NDCG for binary relevance
        assert compute_ndcg(retrieved, RELEVANT, k=3) == pytest.approx(1.0)

    def test_partial_retrieval(self):
        retrieved = _make_retrieved("foo", "qux", "bar")
        score = compute_ndcg(retrieved, RELEVANT, k=3)
        assert 0 < score < 1

    def test_no_relevant_retrieved(self):
        retrieved = _make_retrieved("qux", "quux")
        assert compute_ndcg(retrieved, RELEVANT, k=5) == 0.0

    def test_empty_retrieved(self):
        assert compute_ndcg([], RELEVANT, k=5) == 0.0

    def test_empty_relevant(self):
        assert compute_ndcg([], [], k=5) == 1.0

    def test_k_truncation(self):
        retrieved = _make_retrieved("qux", "quux", "foo", "bar", "baz")
        # k=2 means only qux and quux are considered — both irrelevant
        assert compute_ndcg(retrieved, RELEVANT, k=2) == 0.0
        # k=5 should find all 3 relevant items
        assert compute_ndcg(retrieved, RELEVANT, k=5) > 0


class TestMRR:
    def test_first_is_relevant(self):
        retrieved = _make_retrieved("foo", "qux", "quux")
        assert compute_mrr(retrieved, RELEVANT) == 1.0

    def test_second_is_relevant(self):
        retrieved = _make_retrieved("qux", "bar", "quux")
        assert compute_mrr(retrieved, RELEVANT) == pytest.approx(0.5)

    def test_third_is_relevant(self):
        retrieved = _make_retrieved("qux", "quux", "baz")
        assert compute_mrr(retrieved, RELEVANT) == pytest.approx(1.0 / 3)

    def test_none_relevant(self):
        retrieved = _make_retrieved("qux", "quux")
        assert compute_mrr(retrieved, RELEVANT) == 0.0

    def test_empty(self):
        assert compute_mrr([], RELEVANT) == 0.0


class TestPrecisionAtK:
    def test_all_relevant(self):
        retrieved = _make_retrieved("foo", "bar", "baz")
        assert compute_precision_at_k(retrieved, RELEVANT, k=3) == pytest.approx(1.0)

    def test_half_relevant(self):
        retrieved = _make_retrieved("foo", "qux", "bar", "quux")
        assert compute_precision_at_k(retrieved, RELEVANT, k=4) == pytest.approx(0.5)

    def test_none_relevant(self):
        retrieved = _make_retrieved("qux", "quux")
        assert compute_precision_at_k(retrieved, RELEVANT, k=2) == 0.0


class TestRecallAtK:
    def test_full_recall(self):
        retrieved = _make_retrieved("foo", "bar", "baz")
        assert compute_recall_at_k(retrieved, RELEVANT, k=3) == pytest.approx(1.0)

    def test_partial_recall(self):
        retrieved = _make_retrieved("foo", "qux")
        assert compute_recall_at_k(retrieved, RELEVANT, k=2) == pytest.approx(1.0 / 3)

    def test_no_recall(self):
        retrieved = _make_retrieved("qux", "quux")
        assert compute_recall_at_k(retrieved, RELEVANT, k=2) == 0.0


class TestContextPrecision:
    def test_perfect_context(self):
        retrieved = _make_retrieved("foo", "bar", "baz")
        score = compute_context_precision(retrieved, RELEVANT)
        assert score == pytest.approx(1.0)

    def test_irrelevant_first(self):
        retrieved = _make_retrieved("qux", "foo", "bar", "baz")
        score = compute_context_precision(retrieved, RELEVANT)
        # Lower than perfect because irrelevant item is ranked first
        assert 0 < score < 1


# -- Golden dataset tests --


class TestGoldenDataset:
    def test_roundtrip(self, tmp_path: Path):
        ds = GoldenDataset(
            name="test",
            description="Test dataset",
            repos=["myrepo"],
            queries=[
                GoldenQuery(
                    query="find foo",
                    intent="find",
                    relevant_elements=[{"file_path": "a.py", "name": "foo"}],
                    difficulty="easy",
                    tags=["test"],
                ),
            ],
        )

        path = tmp_path / "test.json"
        ds.to_file(path)
        loaded = GoldenDataset.from_file(path)

        assert loaded.name == "test"
        assert len(loaded.queries) == 1
        assert loaded.queries[0].query == "find foo"
        assert loaded.queries[0].relevant_elements[0]["name"] == "foo"

    def test_load_bundled_dataset(self):
        dataset_path = Path(__file__).parent.parent / "evaluation" / "datasets" / "fastcode_self.json"
        if not dataset_path.exists():
            pytest.skip("Bundled dataset not found")

        ds = GoldenDataset.from_file(dataset_path)
        assert ds.name == "fastcode-self-eval"
        assert len(ds.queries) >= 5

    def test_filter_by_difficulty(self):
        ds = GoldenDataset(
            name="test", description="", repos=[],
            queries=[
                GoldenQuery(query="q1", intent="find", relevant_elements=[], difficulty="easy"),
                GoldenQuery(query="q2", intent="find", relevant_elements=[], difficulty="hard"),
                GoldenQuery(query="q3", intent="find", relevant_elements=[], difficulty="easy"),
            ],
        )
        easy = ds.filter_by_difficulty("easy")
        assert len(easy) == 2

    def test_filter_by_intent(self):
        ds = GoldenDataset(
            name="test", description="", repos=[],
            queries=[
                GoldenQuery(query="q1", intent="how", relevant_elements=[]),
                GoldenQuery(query="q2", intent="what", relevant_elements=[]),
            ],
        )
        assert len(ds.filter_by_intent("how")) == 1


# -- Runner tests --


class TestEvaluationRunner:
    def test_offline_evaluation(self):
        """Test runner in offline mode with pre-computed results."""
        runner = EvaluationRunner(retriever_fn=None)

        retrieved = _make_retrieved("foo", "qux", "bar")
        result = runner.evaluate_query(
            query="find foo",
            relevant_elements=RELEVANT,
            retrieved_elements=retrieved,
        )

        assert result.ndcg_at_10 > 0
        assert result.mrr == 1.0  # foo is first
        assert result.precision_at_5 > 0

    def test_dataset_evaluation_with_mock_retriever(self):
        """Test full dataset evaluation with a mock retriever."""

        def mock_retriever(query: str) -> list[dict]:
            return _make_retrieved("foo", "bar")

        runner = EvaluationRunner(retriever_fn=mock_retriever)
        ds = GoldenDataset(
            name="test", description="", repos=["test"],
            queries=[
                GoldenQuery(
                    query="find foo",
                    intent="find",
                    relevant_elements=[{"file_path": "a.py", "name": "foo"}],
                    difficulty="easy",
                ),
                GoldenQuery(
                    query="find bar",
                    intent="find",
                    relevant_elements=[{"file_path": "b.py", "name": "bar"}],
                    difficulty="medium",
                ),
            ],
        )

        report = runner.evaluate_dataset(ds)
        assert report.num_queries == 2
        assert report.mean_mrr > 0
        assert report.mean_ndcg_at_10 > 0
        assert "find" in report.per_intent

    def test_report_save_and_print(self, tmp_path: Path):
        """Test report serialization."""
        runner = EvaluationRunner(retriever_fn=None)

        result = runner.evaluate_query(
            query="test",
            relevant_elements=RELEVANT,
            retrieved_elements=_make_retrieved("foo", "bar", "baz"),
        )

        # Create a minimal report manually
        from evaluation.runner import EvaluationReport
        report = EvaluationReport(
            dataset_name="test",
            num_queries=1,
            mean_ndcg_at_5=result.ndcg_at_5,
            mean_ndcg_at_10=result.ndcg_at_10,
            mean_mrr=result.mrr,
            mean_precision_at_5=result.precision_at_5,
            mean_recall_at_5=result.recall_at_5,
            mean_recall_at_10=result.recall_at_10,
            mean_context_precision=result.context_precision,
            mean_latency_ms=0,
            per_query=[result],
        )

        # Save
        report_path = tmp_path / "report.json"
        EvaluationRunner.save_report(report, report_path)
        assert report_path.exists()

        data = json.loads(report_path.read_text())
        assert data["dataset_name"] == "test"
        assert data["mean_ndcg_at_10"] > 0

        # Print
        text = EvaluationRunner.print_report(report)
        assert "NDCG@10" in text
        assert "MRR" in text
