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

    def diff(self, workspace_path: str, *, paths: list[str]) -> str: ...

    def commit_to_branch(
        self, workspace_path: str, *, branch: str, base: str,
        paths: list[str], message: str,
    ) -> bool: ...

    def merge_into_base(
        self, repo_ref: str, *, branch: str, base: str, token: str | None = None
    ) -> bool: ...


class ForgeError(Exception):
    """Raised when a git-forge (GitHub) operation fails."""


class GitForgePort(Protocol):
    def installation_token(self) -> str: ...
    def open_pull_request(self, *, head: str, base: str, title: str, body: str) -> str: ...
