from typing import Literal


class FakeGit:
    """Records git calls; deterministic. No filesystem/network."""

    def __init__(self, has_changes: bool = True, memory_diff: str = "", merge_ok: bool = True):
        self._has_changes = has_changes
        self._memory_diff = memory_diff
        self._merge_ok = merge_ok
        self.prepared: list[tuple] = []
        self.committed: list[tuple] = []
        self.pushed: list[tuple] = []
        self.committed_to_branch: list[tuple] = []
        self.merged_into_base: list[tuple] = []
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

    def diff(self, workspace_path: str, *, paths: list[str]) -> str:
        return self._memory_diff

    def commit_to_branch(
        self, workspace_path: str, *, branch: str, base: str,
        paths: list[str], message: str,
    ) -> bool:
        if self._memory_diff:
            self.committed_to_branch.append(
                (workspace_path, branch, base, tuple(paths), message))
            return True
        return False

    def merge_into_base(
        self, repo_ref: str, *, branch: str, base: str, token: str | None = None
    ) -> bool:
        self.merged_into_base.append((repo_ref, branch, base))
        return self._merge_ok


class FakeGitForge:
    """Records token mints + PRs; returns canned values. No network."""

    def __init__(self) -> None:
        self.token_mints = 0
        self.opened: list[tuple] = []

    def installation_token(self) -> str:
        self.token_mints += 1
        return "fake-token"

    def open_pull_request(self, *, head, base, title, body) -> str:
        self.opened.append((head, base, title, body))
        return "https://github.com/fake/fake/pull/1"
