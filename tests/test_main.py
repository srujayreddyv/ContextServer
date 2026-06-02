"""Tests for server.main entry point."""

import os
import sys

import pytest

from server.main import _parse_args, _validate_repo_root


class TestParseArgs:
    """CLI argument parsing."""

    def test_defaults(self):
        args = _parse_args([])
        assert args.repo_root is None
        assert args.transport == "stdio"

    def test_repo_root(self, tmp_path):
        args = _parse_args(["--repo-root", str(tmp_path)])
        assert args.repo_root == str(tmp_path)

    def test_transport_stdio(self):
        args = _parse_args(["--transport", "stdio"])
        assert args.transport == "stdio"

    def test_transport_sse(self):
        args = _parse_args(["--transport", "sse"])
        assert args.transport == "sse"

    def test_invalid_transport(self):
        with pytest.raises(SystemExit):
            _parse_args(["--transport", "invalid"])


class TestValidateRepoRoot:
    """Repository root validation."""

    def test_valid_directory(self, tmp_path):
        result = _validate_repo_root(str(tmp_path))
        assert result == os.path.realpath(str(tmp_path))

    def test_nonexistent_path(self, tmp_path):
        bad_path = str(tmp_path / "does_not_exist")
        with pytest.raises(SystemExit) as exc_info:
            _validate_repo_root(bad_path)
        assert exc_info.value.code == 1

    def test_file_not_directory(self, tmp_path):
        file_path = tmp_path / "afile.txt"
        file_path.write_text("hello")
        with pytest.raises(SystemExit) as exc_info:
            _validate_repo_root(str(file_path))
        assert exc_info.value.code == 1

    def test_resolves_symlinks(self, tmp_path):
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        link = tmp_path / "link"
        link.symlink_to(real_dir)
        result = _validate_repo_root(str(link))
        assert result == os.path.realpath(str(real_dir))
