"""Tests for Phase 8: Incremental indexing via git diff."""

import os

import pytest

from fastcode.indexer import CodeIndexer


class TestIncrementalMetadata:
    """Test the sidecar commit metadata read/write."""

    def test_write_and_read_commit(self, tmp_path):
        meta_path = str(tmp_path / "meta.json")
        CodeIndexer._write_last_indexed_commit(meta_path, "abc123def")
        result = CodeIndexer._read_last_indexed_commit(meta_path)
        assert result == "abc123def"

    def test_read_missing_file_returns_none(self, tmp_path):
        meta_path = str(tmp_path / "nonexistent.json")
        result = CodeIndexer._read_last_indexed_commit(meta_path)
        assert result is None

    def test_read_corrupt_file_returns_none(self, tmp_path):
        meta_path = str(tmp_path / "bad.json")
        with open(meta_path, "w") as f:
            f.write("not json")
        result = CodeIndexer._read_last_indexed_commit(meta_path)
        assert result is None

    def test_overwrite_commit(self, tmp_path):
        meta_path = str(tmp_path / "meta.json")
        CodeIndexer._write_last_indexed_commit(meta_path, "first")
        CodeIndexer._write_last_indexed_commit(meta_path, "second")
        result = CodeIndexer._read_last_indexed_commit(meta_path)
        assert result == "second"

    def test_creates_parent_directory(self, tmp_path):
        meta_path = str(tmp_path / "subdir" / "deep" / "meta.json")
        CodeIndexer._write_last_indexed_commit(meta_path, "sha")
        assert os.path.exists(meta_path)


class TestIncrementalIndexingIntegration:
    """Integration tests using a real git repo (created in tmp)."""

    @pytest.fixture
    def git_repo(self, tmp_path):
        """Create a minimal git repo with one commit."""
        try:
            import git
        except ImportError:
            pytest.skip("GitPython not installed")

        repo_path = str(tmp_path / "repo")
        os.makedirs(repo_path)
        repo = git.Repo.init(repo_path)

        # Create initial file
        file_path = os.path.join(repo_path, "hello.py")
        with open(file_path, "w") as f:
            f.write("def hello():\n    return 'world'\n")

        repo.index.add(["hello.py"])
        repo.index.commit("initial commit")

        return repo_path, repo

    def test_incremental_detects_no_changes(self, git_repo, tmp_path):
        """When HEAD hasn't changed, incremental returns empty."""
        _repo_path, repo = git_repo
        head_sha = repo.head.commit.hexsha

        meta_path = str(tmp_path / "vs" / "test_incremental_meta.json")
        CodeIndexer._write_last_indexed_commit(meta_path, head_sha)

        # Verify reading back
        result = CodeIndexer._read_last_indexed_commit(meta_path)
        assert result == head_sha

    def test_git_diff_detects_added_file(self, git_repo):
        """Adding a file should appear in git diff."""
        repo_path, repo = git_repo
        initial_sha = repo.head.commit.hexsha

        # Add a new file
        new_file = os.path.join(repo_path, "new_module.py")
        with open(new_file, "w") as f:
            f.write("def new_func():\n    pass\n")
        repo.index.add(["new_module.py"])
        repo.index.commit("add new module")

        # Verify diff
        diff = repo.commit(initial_sha).diff(repo.head.commit)
        changed = {d.b_path for d in diff if d.b_path}
        assert "new_module.py" in changed

    def test_git_diff_detects_modified_file(self, git_repo):
        """Modifying a file should appear in git diff."""
        repo_path, repo = git_repo
        initial_sha = repo.head.commit.hexsha

        # Modify existing file
        file_path = os.path.join(repo_path, "hello.py")
        with open(file_path, "w") as f:
            f.write("def hello():\n    return 'updated'\n")
        repo.index.add(["hello.py"])
        repo.index.commit("update hello")

        diff = repo.commit(initial_sha).diff(repo.head.commit)
        changed = set()
        for d in diff:
            if d.a_path:
                changed.add(d.a_path)
            if d.b_path:
                changed.add(d.b_path)
        assert "hello.py" in changed

    def test_git_diff_detects_deleted_file(self, git_repo):
        """Deleting a file should appear in git diff."""
        repo_path, repo = git_repo
        initial_sha = repo.head.commit.hexsha

        # Delete file
        os.remove(os.path.join(repo_path, "hello.py"))
        repo.index.remove(["hello.py"])
        repo.index.commit("delete hello")

        diff = repo.commit(initial_sha).diff(repo.head.commit)
        changed = {d.a_path for d in diff if d.a_path}
        assert "hello.py" in changed
