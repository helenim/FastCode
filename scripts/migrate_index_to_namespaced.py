#!/usr/bin/env python3
"""Migrate FastCode's flat single-repo index layout to a namespaced one.

Today FastCode persists vector / metadata / overview artifacts directly under
``persist_dir`` as ``<repo>.faiss`` / ``<repo>_metadata.{jsonl,pkl}`` /
``repo_overviews.pkl``. The workspace-aware MCP facade (Initiative 2)
introduced a per-tenant namespace, so we want each tenant's artifacts to
live under their own subdirectory::

    <persist_dir>/<namespace>/<repo>.faiss
    <persist_dir>/<namespace>/<repo>_metadata.jsonl
    <persist_dir>/<namespace>/<repo>_metadata.pkl
    <persist_dir>/<namespace>/repo_overviews.pkl

This script is the migration tool. It can:

* Plan a forward migration (flat → namespaced) — default ``--mode forward``.
* Plan a rollback (namespaced → flat) for emergency revert — ``--mode rollback``.

Defaults to ``--dry-run`` so the operator can review the planned moves
before anything touches disk. The script never deletes data — every move
is a ``shutil.move`` so power loss leaves the operator with either the old
or the new layout, never half-overwritten files.

The companion FastCode reader path (``vector_store.py``) still expects the
flat layout. Run this script only AFTER the paired vector-store change
lands; otherwise the FastCode engine will be unable to find its artifacts.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_NAMESPACE = "_default"
TRACKED_SUFFIXES = (".faiss", "_metadata.jsonl", "_metadata.pkl")
GLOBAL_FILES = ("repo_overviews.pkl",)


@dataclass(frozen=True)
class MovePlan:
    src: Path
    dst: Path
    reason: str

    def render(self) -> str:
        try:
            return f"{self.src.relative_to(Path.cwd())} → {self.dst.relative_to(Path.cwd())}  [{self.reason}]"
        except ValueError:
            return f"{self.src} → {self.dst}  [{self.reason}]"


def _plan_forward(persist_dir: Path, namespace: str) -> list[MovePlan]:
    plans: list[MovePlan] = []
    target_dir = persist_dir / namespace
    for entry in sorted(persist_dir.iterdir()):
        if not entry.is_file():
            continue
        # Skip files already inside the namespace dir (we walk depth=1 only).
        if entry.parent != persist_dir:
            continue
        if entry.name in GLOBAL_FILES:
            plans.append(MovePlan(entry, target_dir / entry.name, "global overview file"))
            continue
        for suffix in TRACKED_SUFFIXES:
            if entry.name.endswith(suffix):
                plans.append(MovePlan(entry, target_dir / entry.name, f"index artifact ({suffix})"))
                break
    return plans


def _plan_rollback(persist_dir: Path, namespace: str) -> list[MovePlan]:
    plans: list[MovePlan] = []
    src_dir = persist_dir / namespace
    if not src_dir.is_dir():
        return plans
    for entry in sorted(src_dir.iterdir()):
        if not entry.is_file():
            continue
        if entry.name in GLOBAL_FILES or any(entry.name.endswith(s) for s in TRACKED_SUFFIXES):
            plans.append(MovePlan(entry, persist_dir / entry.name, f"rollback {namespace}"))
    return plans


def execute(plans: list[MovePlan]) -> tuple[int, list[str]]:
    moved = 0
    errors: list[str] = []
    for plan in plans:
        if plan.dst.exists():
            errors.append(f"target exists, refusing to overwrite: {plan.dst}")
            continue
        plan.dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(plan.src), str(plan.dst))
            moved += 1
        except OSError as exc:
            errors.append(f"move failed {plan.src} → {plan.dst}: {exc}")
    return moved, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="migrate_index_to_namespaced",
        description="Migrate FastCode index artifacts to a per-namespace layout.",
    )
    parser.add_argument(
        "persist_dir",
        type=Path,
        help="FastCode persist_dir (e.g. ./data/vector_store).",
    )
    parser.add_argument(
        "--namespace",
        default=DEFAULT_NAMESPACE,
        help=f"Target namespace (default: {DEFAULT_NAMESPACE!r}).",
    )
    parser.add_argument(
        "--mode",
        choices=("forward", "rollback"),
        default="forward",
        help="forward = flat → namespaced; rollback = namespaced → flat.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Plan only, do not move anything (default).",
    )
    parser.add_argument(
        "--apply",
        dest="dry_run",
        action="store_false",
        help="Actually perform the moves. Without this flag the run is a dry-run.",
    )
    args = parser.parse_args(argv)

    persist_dir: Path = args.persist_dir.resolve()
    if not persist_dir.is_dir():
        print(f"error: {persist_dir} is not a directory", file=sys.stderr)
        return 2

    if args.mode == "forward":
        plans = _plan_forward(persist_dir, args.namespace)
    else:
        plans = _plan_rollback(persist_dir, args.namespace)

    print(f"persist_dir: {persist_dir}")
    print(f"namespace:   {args.namespace}")
    print(f"mode:        {args.mode}")
    print(f"planned:     {len(plans)} file moves")
    for plan in plans:
        print(f"  - {plan.render()}")

    if args.dry_run:
        print("\n(dry-run — pass --apply to perform the moves)")
        return 0

    moved, errors = execute(plans)
    print(f"\nmoved: {moved} file(s)")
    if errors:
        print("errors:")
        for err in errors:
            print(f"  - {err}")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
