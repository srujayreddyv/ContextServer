"""Unit tests for path_utils module."""

import os
import pytest
from server.path_utils import PathContainmentError, resolve_and_validate


class TestResolveAndValidate:
    """Tests for resolve_and_validate()."""

    def test_valid_relative_path(self, tmp_path):
        """A simple relative path within the repo resolves correctly."""
        target = tmp_path / "hello.txt"
        target.write_text("hi")
        result = resolve_and_validate("hello.txt", str(tmp_path))
        assert result == str(target.resolve())

    def test_valid_nested_path(self, tmp_path):
        """A nested relative path within the repo resolves correctly."""
        sub = tmp_path / "a" / "b"
        sub.mkdir(parents=True)
        target = sub / "file.txt"
        target.write_text("data")
        result = resolve_and_validate("a/b/file.txt", str(tmp_path))
        assert result == str(target.resolve())

    def test_repo_root_itself(self, tmp_path):
        """Passing '.' or '' should resolve to the repo root itself."""
        result = resolve_and_validate(".", str(tmp_path))
        assert result == os.path.realpath(str(tmp_path))

    def test_dot_dot_traversal_raises(self, tmp_path):
        """A path with ../ that escapes the repo root raises PathContainmentError."""
        with pytest.raises(PathContainmentError):
            resolve_and_validate("../outside", str(tmp_path))

    def test_deep_dot_dot_traversal_raises(self, tmp_path):
        """Multiple ../ segments that escape the repo root raise PathContainmentError."""
        with pytest.raises(PathContainmentError):
            resolve_and_validate("a/../../outside", str(tmp_path))

    def test_absolute_path_outside_raises(self, tmp_path):
        """An absolute path outside the repo root raises PathContainmentError."""
        with pytest.raises(PathContainmentError):
            resolve_and_validate("/tmp/evil", str(tmp_path))

    def test_absolute_path_inside_allowed(self, tmp_path):
        """An absolute path that is inside the repo root is allowed."""
        target = tmp_path / "ok.txt"
        target.write_text("fine")
        result = resolve_and_validate(str(target), str(tmp_path))
        assert result == str(target.resolve())

    def test_symlink_inside_repo_allowed(self, tmp_path):
        """A symlink pointing to a file inside the repo is allowed."""
        real = tmp_path / "real.txt"
        real.write_text("content")
        link = tmp_path / "link.txt"
        link.symlink_to(real)
        result = resolve_and_validate("link.txt", str(tmp_path))
        assert result == str(real.resolve())

    def test_symlink_escaping_repo_raises(self, tmp_path):
        """A symlink pointing outside the repo root raises PathContainmentError."""
        outside = tmp_path.parent / "outside_target.txt"
        outside.write_text("secret")
        link = tmp_path / "escape_link"
        link.symlink_to(outside)
        with pytest.raises(PathContainmentError):
            resolve_and_validate("escape_link", str(tmp_path))
        # cleanup
        outside.unlink()

    def test_error_message_contains_details(self, tmp_path):
        """The error message includes the offending path and repo root."""
        with pytest.raises(PathContainmentError, match="outside the repository root"):
            resolve_and_validate("../escape", str(tmp_path))

    def test_prefix_false_positive(self, tmp_path):
        """A sibling directory whose name starts with the repo root name is rejected."""
        # e.g. repo root is /tmp/repo, sibling is /tmp/repo-extra
        sibling = tmp_path.parent / (tmp_path.name + "-extra")
        sibling.mkdir(exist_ok=True)
        target = sibling / "file.txt"
        target.write_text("data")
        with pytest.raises(PathContainmentError):
            resolve_and_validate(str(target), str(tmp_path))
        # cleanup
        target.unlink()
        sibling.rmdir()
