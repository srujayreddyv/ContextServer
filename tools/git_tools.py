"""Git tools: git_log, git_diff, git_status, git_branches.

All git operations shell out to the ``git`` CLI via subprocess.
A module-level ``_repo_root`` is set via ``set_repo_root()`` before tool use.
"""

import os
import shutil
import subprocess

from server.tool_registry import ToolDefinition

# Module-level repo root, set via ``set_repo_root()`` before tool use.
_repo_root: str = ""


def set_repo_root(repo_root: str) -> None:
    """Configure the repository root used by all git tools."""
    global _repo_root
    _repo_root = repo_root


class GitNotAvailableError(Exception):
    """Repository has no .git directory or git CLI not found."""


class GitRefNotFoundError(Exception):
    """Invalid commit reference."""


# --------------- helpers ---------------

_COMMIT_SEP = "---commit-separator---"


def _check_git_available() -> None:
    """Raise ``GitNotAvailableError`` if git CLI is missing or no .git dir."""
    if not shutil.which("git"):
        raise GitNotAvailableError("git CLI not found on PATH")
    git_dir = os.path.join(os.path.realpath(_repo_root), ".git")
    if not os.path.isdir(git_dir):
        raise GitNotAvailableError(
            f"No .git directory found in repository root: {_repo_root}"
        )


# --------------- git_log ---------------


async def git_log(params: dict) -> list[dict]:
    """Retrieve recent git commits.

    Args:
        params: Dict with keys:
            - ``max_count`` (int, optional): Maximum commits to return (default 10).
            - ``file_path`` (str, optional): Only commits that modified this file.

    Returns:
        List of dicts with ``hash``, ``author``, ``date``, ``message``.

    Raises:
        GitNotAvailableError: If ``.git`` absent or ``git`` CLI not found.
    """
    _check_git_available()

    max_count = params.get("max_count", 10)
    file_path = params.get("file_path")

    fmt = f"%H%n%an%n%aI%n%s%n{_COMMIT_SEP}"
    cmd = ["git", "log", f"--max-count={max_count}", f"--format={fmt}"]

    if file_path:
        cmd.append("--")
        cmd.append(file_path)

    result = subprocess.run(
        cmd,
        cwd=os.path.realpath(_repo_root),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        # Empty repo or other git error — return empty list
        return []

    return _parse_log_output(result.stdout)


def _parse_log_output(output: str) -> list[dict]:
    """Parse ``git log`` output into commit dicts."""
    commits: list[dict] = []
    raw_commits = output.strip().split(_COMMIT_SEP)

    for block in raw_commits:
        lines = block.strip().splitlines()
        if len(lines) < 4:
            continue
        commits.append(
            {
                "hash": lines[0].strip(),
                "author": lines[1].strip(),
                "date": lines[2].strip(),
                "message": lines[3].strip(),
            }
        )

    return commits


# --------------- JSON Schema for git_log ---------------

GIT_LOG_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "max_count": {
            "type": "integer",
            "description": "Maximum number of commits to return (default 10)",
        },
        "file_path": {
            "type": "string",
            "description": "Only return commits that modified this file path (optional)",
        },
    },
    "required": [],
}


def make_git_log_tool() -> ToolDefinition:
    """Create a ToolDefinition for the git_log tool."""
    return ToolDefinition(
        name="git_log",
        description="Retrieve recent Git commit history, optionally filtered by file.",
        parameters=GIT_LOG_SCHEMA,
        handler=git_log,
    )


# --------------- git_diff ---------------


def _verify_git_ref(ref: str) -> None:
    """Raise ``GitRefNotFoundError`` if *ref* is not a valid git reference."""
    result = subprocess.run(
        ["git", "rev-parse", "--verify", ref],
        cwd=os.path.realpath(_repo_root),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GitRefNotFoundError(f"Invalid commit reference: {ref}")


async def git_diff(params: dict) -> str:
    """Return diff text for the repository.

    Behaviour based on supplied refs:
    - No refs → diff of uncommitted working-tree changes (``git diff``).
    - One ref (``ref1``) → diff between that ref and the working tree.
    - Two refs (``ref1``, ``ref2``) → diff between the two refs.

    Args:
        params: Dict with optional keys ``ref1`` and ``ref2``.

    Returns:
        Diff text (may be empty if there are no differences).

    Raises:
        GitNotAvailableError: If ``.git`` absent or ``git`` CLI not found.
        GitRefNotFoundError: If a supplied commit reference is invalid.
    """
    _check_git_available()

    ref1 = params.get("ref1")
    ref2 = params.get("ref2")

    # Validate refs before running diff
    if ref1:
        _verify_git_ref(ref1)
    if ref2:
        _verify_git_ref(ref2)

    cmd = ["git", "diff"]
    if ref1 and ref2:
        cmd.extend([ref1, ref2])
    elif ref1:
        cmd.append(ref1)
    # else: no refs → working tree diff

    result = subprocess.run(
        cmd,
        cwd=os.path.realpath(_repo_root),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return ""

    return result.stdout


# --------------- JSON Schema for git_diff ---------------

GIT_DIFF_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "ref1": {
            "type": "string",
            "description": "First commit reference (optional)",
        },
        "ref2": {
            "type": "string",
            "description": "Second commit reference (optional)",
        },
    },
    "required": [],
}


def make_git_diff_tool() -> ToolDefinition:
    """Create a ToolDefinition for the git_diff tool."""
    return ToolDefinition(
        name="git_diff",
        description="Show diffs between commits or the working tree.",
        parameters=GIT_DIFF_SCHEMA,
        handler=git_diff,
    )


# --------------- git_status ---------------


async def git_status(params: dict) -> dict:
    """Return current branch, modified, staged, and untracked files.

    Uses ``git status --porcelain=v1 --branch`` to parse output.

    Returns:
        Dict with ``branch``, ``modified``, ``staged``, ``untracked``.

    Raises:
        GitNotAvailableError: If ``.git`` absent or ``git`` CLI not found.
    """
    _check_git_available()

    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "--branch"],
        cwd=os.path.realpath(_repo_root),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise GitNotAvailableError(
            f"git status failed: {result.stderr.strip()}"
        )

    branch = ""
    modified: list[str] = []
    staged: list[str] = []
    untracked: list[str] = []

    for line in result.stdout.splitlines():
        if line.startswith("## "):
            # e.g. "## main...origin/main" or "## main" or "## No commits yet on main"
            branch_part = line[3:]
            # Handle "No commits yet on <branch>"
            if branch_part.startswith("No commits yet on "):
                branch = branch_part[len("No commits yet on "):]
            else:
                # Strip tracking info after "..."
                branch = branch_part.split("...")[0]
            continue

        if len(line) < 2:
            continue

        index_status = line[0]
        worktree_status = line[1]
        # File path starts at position 3
        file_path = line[3:]

        # Handle renames: "R  old -> new"
        if " -> " in file_path:
            file_path = file_path.split(" -> ")[-1]

        # Staged: index has a letter (A, M, D, R, C) and it's not '?' or '!'
        if index_status in ("A", "M", "D", "R", "C"):
            staged.append(file_path)

        # Modified in worktree
        if worktree_status == "M":
            modified.append(file_path)

        # Untracked
        if index_status == "?" and worktree_status == "?":
            untracked.append(file_path)

    return {
        "branch": branch,
        "modified": modified,
        "staged": staged,
        "untracked": untracked,
    }


# --------------- JSON Schema for git_status ---------------

GIT_STATUS_SCHEMA: dict = {
    "type": "object",
    "properties": {},
    "required": [],
}


def make_git_status_tool() -> ToolDefinition:
    """Create a ToolDefinition for the git_status tool."""
    return ToolDefinition(
        name="git_status",
        description="Return current branch name and lists of modified, staged, and untracked files.",
        parameters=GIT_STATUS_SCHEMA,
        handler=git_status,
    )


# --------------- git_branches ---------------


async def git_branches(params: dict) -> list[dict]:
    """Return list of local branches with ``is_current`` flag.

    Uses ``git branch --list`` and parses the output.

    Returns:
        List of dicts with ``name`` and ``is_current``.

    Raises:
        GitNotAvailableError: If ``.git`` absent or ``git`` CLI not found.
    """
    _check_git_available()

    result = subprocess.run(
        ["git", "branch", "--list"],
        cwd=os.path.realpath(_repo_root),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise GitNotAvailableError(
            f"git branch failed: {result.stderr.strip()}"
        )

    branches: list[dict] = []
    for line in result.stdout.splitlines():
        line = line.rstrip()
        if not line:
            continue
        is_current = line.startswith("* ")
        name = line[2:].strip()
        # Skip detached HEAD entries like "* (HEAD detached at ...)"
        if name.startswith("("):
            continue
        branches.append({"name": name, "is_current": is_current})

    return branches


# --------------- JSON Schema for git_branches ---------------

GIT_BRANCHES_SCHEMA: dict = {
    "type": "object",
    "properties": {},
    "required": [],
}


def make_git_branches_tool() -> ToolDefinition:
    """Create a ToolDefinition for the git_branches tool."""
    return ToolDefinition(
        name="git_branches",
        description="Return list of local branches with an indicator for the currently checked-out branch.",
        parameters=GIT_BRANCHES_SCHEMA,
        handler=git_branches,
    )
