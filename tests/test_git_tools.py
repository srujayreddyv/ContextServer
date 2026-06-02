"""Unit tests for git_tools: git_log."""

import os
import subprocess

import pytest

from tools.git_tools import (
    GitNotAvailableError,
    GitRefNotFoundError,
    git_branches,
    git_diff,
    git_log,
    git_status,
    make_git_branches_tool,
    make_git_diff_tool,
    make_git_log_tool,
    make_git_status_tool,
    set_repo_root,
)


def _run_git(cwd, *args):
    """Helper to run a git command in a directory."""
    subprocess.run(
        ["git"] + list(args),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repo with a few commits."""
    _run_git(tmp_path, "init")
    _run_git(tmp_path, "config", "user.email", "test@example.com")
    _run_git(tmp_path, "config", "user.name", "Test User")

    # Commit 1: add file_a.txt
    (tmp_path / "file_a.txt").write_text("hello\n", encoding="utf-8")
    _run_git(tmp_path, "add", "file_a.txt")
    _run_git(tmp_path, "commit", "-m", "Add file_a")

    # Commit 2: add file_b.txt
    (tmp_path / "file_b.txt").write_text("world\n", encoding="utf-8")
    _run_git(tmp_path, "add", "file_b.txt")
    _run_git(tmp_path, "commit", "-m", "Add file_b")

    # Commit 3: modify file_a.txt
    (tmp_path / "file_a.txt").write_text("hello updated\n", encoding="utf-8")
    _run_git(tmp_path, "add", "file_a.txt")
    _run_git(tmp_path, "commit", "-m", "Update file_a")

    set_repo_root(str(tmp_path))
    return tmp_path


# --------------- basic git_log ---------------


@pytest.mark.asyncio
async def test_git_log_returns_commits(git_repo):
    result = await git_log({})
    assert len(result) == 3
    # Most recent commit first
    assert result[0]["message"] == "Update file_a"
    assert result[1]["message"] == "Add file_b"
    assert result[2]["message"] == "Add file_a"


@pytest.mark.asyncio
async def test_git_log_commit_fields(git_repo):
    result = await git_log({})
    for commit in result:
        assert commit["hash"]  # non-empty
        assert len(commit["hash"]) == 40  # full SHA
        assert commit["author"] == "Test User"
        assert commit["date"]  # non-empty ISO date
        assert commit["message"]  # non-empty


# --------------- max_count ---------------


@pytest.mark.asyncio
async def test_git_log_max_count(git_repo):
    result = await git_log({"max_count": 2})
    assert len(result) == 2
    assert result[0]["message"] == "Update file_a"
    assert result[1]["message"] == "Add file_b"


@pytest.mark.asyncio
async def test_git_log_max_count_exceeds_total(git_repo):
    result = await git_log({"max_count": 100})
    assert len(result) == 3


@pytest.mark.asyncio
async def test_git_log_max_count_one(git_repo):
    result = await git_log({"max_count": 1})
    assert len(result) == 1
    assert result[0]["message"] == "Update file_a"


# --------------- file_path filter ---------------


@pytest.mark.asyncio
async def test_git_log_file_path_filter(git_repo):
    result = await git_log({"file_path": "file_b.txt"})
    assert len(result) == 1
    assert result[0]["message"] == "Add file_b"


@pytest.mark.asyncio
async def test_git_log_file_path_multiple_commits(git_repo):
    result = await git_log({"file_path": "file_a.txt"})
    assert len(result) == 2
    assert result[0]["message"] == "Update file_a"
    assert result[1]["message"] == "Add file_a"


@pytest.mark.asyncio
async def test_git_log_file_path_with_max_count(git_repo):
    result = await git_log({"file_path": "file_a.txt", "max_count": 1})
    assert len(result) == 1
    assert result[0]["message"] == "Update file_a"


# --------------- error: no .git directory ---------------


@pytest.mark.asyncio
async def test_git_log_no_git_dir(tmp_path):
    set_repo_root(str(tmp_path))
    with pytest.raises(GitNotAvailableError, match="No .git directory"):
        await git_log({})


# --------------- make_git_log_tool ---------------


def test_make_git_log_tool_returns_definition():
    tool = make_git_log_tool()
    assert tool.name == "git_log"
    assert "max_count" in tool.parameters["properties"]
    assert "file_path" in tool.parameters["properties"]
    assert tool.handler is git_log


# --------------- git_diff: no refs (working tree) ---------------


@pytest.mark.asyncio
async def test_git_diff_no_refs_clean_tree(git_repo):
    """No uncommitted changes → empty diff."""
    result = await git_diff({})
    assert result == ""


@pytest.mark.asyncio
async def test_git_diff_no_refs_with_changes(git_repo):
    """Uncommitted modification shows in diff."""
    (git_repo / "file_a.txt").write_text("changed content\n", encoding="utf-8")
    result = await git_diff({})
    assert "changed content" in result
    assert "diff --git" in result


# --------------- git_diff: one ref ---------------


@pytest.mark.asyncio
async def test_git_diff_one_ref_vs_working_tree(git_repo):
    """Diff between a commit and the working tree."""
    # Get the first commit hash (oldest)
    commits = await git_log({"max_count": 100})
    first_commit = commits[-1]["hash"]

    # Working tree matches HEAD (3rd commit), so diff vs first commit
    result = await git_diff({"ref1": first_commit})
    # file_a.txt was "hello\n" in first commit, now "hello updated\n"
    assert "hello updated" in result


@pytest.mark.asyncio
async def test_git_diff_one_ref_head(git_repo):
    """Diff HEAD vs working tree with no changes → empty."""
    result = await git_diff({"ref1": "HEAD"})
    assert result == ""


# --------------- git_diff: two refs ---------------


@pytest.mark.asyncio
async def test_git_diff_two_refs(git_repo):
    """Diff between two specific commits."""
    commits = await git_log({"max_count": 100})
    oldest = commits[-1]["hash"]
    newest = commits[0]["hash"]

    result = await git_diff({"ref1": oldest, "ref2": newest})
    assert "diff --git" in result
    # file_b.txt was added between first and last commit
    assert "file_b.txt" in result


# --------------- git_diff: invalid refs ---------------


@pytest.mark.asyncio
async def test_git_diff_invalid_ref1(git_repo):
    """Invalid ref1 raises GitRefNotFoundError."""
    with pytest.raises(GitRefNotFoundError, match="Invalid commit reference"):
        await git_diff({"ref1": "nonexistent_ref_abc123"})


@pytest.mark.asyncio
async def test_git_diff_invalid_ref2(git_repo):
    """Invalid ref2 raises GitRefNotFoundError."""
    with pytest.raises(GitRefNotFoundError, match="Invalid commit reference"):
        await git_diff({"ref1": "HEAD", "ref2": "nonexistent_ref_xyz789"})


# --------------- git_diff: no .git directory ---------------


@pytest.mark.asyncio
async def test_git_diff_no_git_dir(tmp_path):
    """No .git directory raises GitNotAvailableError."""
    set_repo_root(str(tmp_path))
    with pytest.raises(GitNotAvailableError, match="No .git directory"):
        await git_diff({})


# --------------- make_git_diff_tool ---------------


def test_make_git_diff_tool_returns_definition():
    tool = make_git_diff_tool()
    assert tool.name == "git_diff"
    assert "ref1" in tool.parameters["properties"]
    assert "ref2" in tool.parameters["properties"]
    assert tool.handler is git_diff


# ===============================================================
# git_status tests
# ===============================================================


@pytest.mark.asyncio
async def test_git_status_clean_repo(git_repo):
    """Clean repo reports branch and empty file lists."""
    result = await git_status({})
    assert result["branch"]  # non-empty branch name
    assert result["modified"] == []
    assert result["staged"] == []
    assert result["untracked"] == []


@pytest.mark.asyncio
async def test_git_status_modified_file(git_repo):
    """Modified but unstaged file appears in 'modified'."""
    (git_repo / "file_a.txt").write_text("changed\n", encoding="utf-8")
    result = await git_status({})
    assert "file_a.txt" in result["modified"]
    assert "file_a.txt" not in result["staged"]
    assert "file_a.txt" not in result["untracked"]


@pytest.mark.asyncio
async def test_git_status_staged_file(git_repo):
    """Staged file appears in 'staged'."""
    (git_repo / "file_a.txt").write_text("staged change\n", encoding="utf-8")
    _run_git(git_repo, "add", "file_a.txt")
    result = await git_status({})
    assert "file_a.txt" in result["staged"]


@pytest.mark.asyncio
async def test_git_status_untracked_file(git_repo):
    """New untracked file appears in 'untracked'."""
    (git_repo / "new_file.txt").write_text("new\n", encoding="utf-8")
    result = await git_status({})
    assert "new_file.txt" in result["untracked"]
    assert "new_file.txt" not in result["modified"]
    assert "new_file.txt" not in result["staged"]


@pytest.mark.asyncio
async def test_git_status_mixed(git_repo):
    """Multiple file states at once."""
    # Modified (unstaged)
    (git_repo / "file_a.txt").write_text("mod\n", encoding="utf-8")
    # Staged new file
    (git_repo / "staged_new.txt").write_text("s\n", encoding="utf-8")
    _run_git(git_repo, "add", "staged_new.txt")
    # Untracked
    (git_repo / "untracked.txt").write_text("u\n", encoding="utf-8")

    result = await git_status({})
    assert "file_a.txt" in result["modified"]
    assert "staged_new.txt" in result["staged"]
    assert "untracked.txt" in result["untracked"]


@pytest.mark.asyncio
async def test_git_status_branch_name(git_repo):
    """Branch name is reported correctly."""
    # The default branch created by git init
    result = await git_status({})
    # Could be "main" or "master" depending on git config
    assert isinstance(result["branch"], str)
    assert len(result["branch"]) > 0


@pytest.mark.asyncio
async def test_git_status_no_git_dir(tmp_path):
    """No .git directory raises GitNotAvailableError."""
    set_repo_root(str(tmp_path))
    with pytest.raises(GitNotAvailableError, match="No .git directory"):
        await git_status({})


# --------------- make_git_status_tool ---------------


def test_make_git_status_tool_returns_definition():
    tool = make_git_status_tool()
    assert tool.name == "git_status"
    assert tool.handler is git_status


# ===============================================================
# git_branches tests
# ===============================================================


@pytest.mark.asyncio
async def test_git_branches_single_branch(git_repo):
    """Repo with one branch returns it as current."""
    result = await git_branches({})
    assert len(result) >= 1
    current = [b for b in result if b["is_current"]]
    assert len(current) == 1
    assert current[0]["name"]  # non-empty


@pytest.mark.asyncio
async def test_git_branches_multiple_branches(git_repo):
    """Creating extra branches shows them all, with exactly one current."""
    _run_git(git_repo, "branch", "feature-x")
    _run_git(git_repo, "branch", "feature-y")

    result = await git_branches({})
    names = [b["name"] for b in result]
    assert "feature-x" in names
    assert "feature-y" in names

    current = [b for b in result if b["is_current"]]
    assert len(current) == 1


@pytest.mark.asyncio
async def test_git_branches_after_checkout(git_repo):
    """After switching branches, is_current reflects the new branch."""
    _run_git(git_repo, "branch", "dev")
    _run_git(git_repo, "checkout", "dev")

    result = await git_branches({})
    current = [b for b in result if b["is_current"]]
    assert len(current) == 1
    assert current[0]["name"] == "dev"


@pytest.mark.asyncio
async def test_git_branches_no_git_dir(tmp_path):
    """No .git directory raises GitNotAvailableError."""
    set_repo_root(str(tmp_path))
    with pytest.raises(GitNotAvailableError, match="No .git directory"):
        await git_branches({})


# --------------- make_git_branches_tool ---------------


def test_make_git_branches_tool_returns_definition():
    tool = make_git_branches_tool()
    assert tool.name == "git_branches"
    assert tool.handler is git_branches
