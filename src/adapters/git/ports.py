from typing import Literal, Protocol


class GitError(Exception):
    """Raised when a git operation fails."""


class GitPort(Protocol):
    def prepare(
        self,
        *,
        repo_ref: str,
        workspace_path: str,
        branch: str,
        mode: Literal["worktree", "clone"],
        token: str | None = None,
    ) -> None: ...

    def commit_all(self, workspace_path: str, message: str) -> bool: ...

    def push(self, workspace_path: str, branch: str, *, token: str | None = None) -> None: ...

    def current_branch(self, workspace_path: str) -> str: ...
