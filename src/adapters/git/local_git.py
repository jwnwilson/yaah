import base64
import subprocess
from typing import Literal

from adapters.git.ports import GitError

_AUTHOR = ["-c", "user.email=agent@yaah.local", "-c", "user.name=yaah-agent"]


class LocalGit:
    """GitPort via the system `git` binary. `mode='worktree'` adds a worktree off a
    local repo (local profile); `mode='clone'` clones a remote (remote profile)."""

    def _run(self, args: list[str], cwd: str | None = None) -> str:
        proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise GitError(proc.stderr.strip() or f"git {args[0]} failed")
        return proc.stdout

    def _auth_args(self, token: str | None) -> list[str]:
        if not token:
            return []
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        # passed per-invocation; never written to .git/config (no token in remote URL)
        return ["-c", f"http.extraheader=AUTHORIZATION: basic {basic}"]

    def prepare(
        self,
        *,
        repo_ref: str,
        workspace_path: str,
        branch: str,
        mode: Literal["worktree", "clone"],
        token: str | None = None,
    ) -> None:
        if mode == "worktree":
            self._run(["worktree", "add", "-b", branch, workspace_path], cwd=repo_ref)
        else:  # clone
            self._run([*self._auth_args(token), "clone", repo_ref, workspace_path])
            self._run([*_AUTHOR, "checkout", "-b", branch], cwd=workspace_path)

    def commit_all(self, workspace_path: str, message: str) -> bool:
        self._run(["add", "-A"], cwd=workspace_path)
        status = self._run(["status", "--porcelain"], cwd=workspace_path)
        if not status.strip():
            return False
        self._run([*_AUTHOR, "commit", "-m", message], cwd=workspace_path)
        return True

    def push(self, workspace_path: str, branch: str, *, token: str | None = None) -> None:
        self._run([*self._auth_args(token), "push", "origin", branch], cwd=workspace_path)

    def current_branch(self, workspace_path: str) -> str:
        return self._run(["rev-parse", "--abbrev-ref", "HEAD"], cwd=workspace_path).strip()
