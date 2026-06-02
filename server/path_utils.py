"""Path resolution and containment checks.

All file operations must go through resolve_and_validate() to ensure
paths stay within the configured repository root.
"""

import os


class PathContainmentError(Exception):
    """Raised when a path resolves outside the repository root."""


def resolve_and_validate(path: str, repo_root: str) -> str:
    """Resolve a relative path against repo_root, follow symlinks,
    and verify the result is within repo_root.

    Args:
        path: A relative (or absolute) file path to resolve.
        repo_root: The repository root directory.

    Returns:
        The resolved absolute path.

    Raises:
        PathContainmentError: If the resolved path is outside repo_root.
    """
    resolved_root = os.path.realpath(repo_root)
    joined = os.path.join(resolved_root, path)
    resolved_path = os.path.realpath(joined)

    # Ensure the resolved path is the root itself or a child of it.
    # We append os.sep to avoid prefix false positives like
    # /repo-root-extra matching /repo-root.
    if resolved_path != resolved_root and not resolved_path.startswith(
        resolved_root + os.sep
    ):
        raise PathContainmentError(
            f"Path '{path}' resolves to '{resolved_path}', "
            f"which is outside the repository root '{resolved_root}'"
        )

    return resolved_path
