"""
Golden dataset management for retrieval evaluation.

A golden dataset is a JSON file mapping queries to their expected relevant
code elements (identified by file_path + element_name or element_id).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class GoldenQuery:
    """A single evaluation query with expected results."""

    query: str
    intent: str  # how, what, where, debug, explain, find, implement
    relevant_elements: list[dict[str, str]]  # [{"file_path": ..., "name": ..., "type": ...}]
    expected_repos: list[str] = field(default_factory=list)
    difficulty: str = "medium"  # easy, medium, hard
    tags: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class GoldenDataset:
    """Collection of golden queries for a specific repo or repo set."""

    name: str
    description: str
    repos: list[str]
    queries: list[GoldenQuery]
    version: str = "1.0"

    @classmethod
    def from_file(cls, path: str | Path) -> GoldenDataset:
        """Load a golden dataset from a JSON file."""
        path = Path(path)
        with path.open() as f:
            data = json.load(f)

        queries = [
            GoldenQuery(
                query=q["query"],
                intent=q.get("intent", "find"),
                relevant_elements=q["relevant_elements"],
                expected_repos=q.get("expected_repos", []),
                difficulty=q.get("difficulty", "medium"),
                tags=q.get("tags", []),
                notes=q.get("notes", ""),
            )
            for q in data["queries"]
        ]

        return cls(
            name=data["name"],
            description=data.get("description", ""),
            repos=data.get("repos", []),
            queries=queries,
            version=data.get("version", "1.0"),
        )

    def to_file(self, path: str | Path) -> None:
        """Save the golden dataset to a JSON file."""
        path = Path(path)
        data = {
            "name": self.name,
            "description": self.description,
            "repos": self.repos,
            "version": self.version,
            "queries": [
                {
                    "query": q.query,
                    "intent": q.intent,
                    "relevant_elements": q.relevant_elements,
                    "expected_repos": q.expected_repos,
                    "difficulty": q.difficulty,
                    "tags": q.tags,
                    "notes": q.notes,
                }
                for q in self.queries
            ],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            json.dump(data, f, indent=2)
        logger.info("Saved golden dataset '%s' with %d queries to %s", self.name, len(self.queries), path)

    def filter_by_difficulty(self, difficulty: str) -> list[GoldenQuery]:
        """Return queries of a specific difficulty level."""
        return [q for q in self.queries if q.difficulty == difficulty]

    def filter_by_intent(self, intent: str) -> list[GoldenQuery]:
        """Return queries of a specific intent type."""
        return [q for q in self.queries if q.intent == intent]

    def filter_by_tag(self, tag: str) -> list[GoldenQuery]:
        """Return queries that have a specific tag."""
        return [q for q in self.queries if tag in q.tags]
