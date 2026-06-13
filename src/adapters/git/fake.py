from typing import Literal


class FakeGit:
    """Records git calls; deterministic. No filesystem/network."""

    def __init__(self, has_changes: bool = True):
        self._has_changes = has_changes
        self.prepared: list[tuple] = []
        self.committed: list[tuple] = []
        self.pushed: list[tuple] = []
        self._branch = ""

    def prepare(
        self,
        *,
        repo_ref: str,
        workspace_path: str,
        branch: str,
        mode: Literal["worktree", "clone"],
        token: str | None = None,
    ) -> None:
        self.prepared.append((repo_ref, workspace_path, branch, mode))
        self._branch = branch

    def commit_all(self, workspace_path: str, message: str) -> bool:
        if self._has_changes:
            self.committed.append((workspace_path, message))
        return self._has_changes

    def push(self, workspace_path: str, branch: str, *, token: str | None = None) -> None:
        self.pushed.append((workspace_path, branch, token))

    def current_branch(self, workspace_path: str) -> str:
        return self._branch
