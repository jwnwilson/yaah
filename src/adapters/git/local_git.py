import base64
import hashlib
import re
import subprocess
from pathlib import Path
from typing import Literal

from adapters.git.ports import GitError
from domain.orchestration import MergeResult

_AUTHOR = ["-c", "user.email=agent@yaah.local", "-c", "user.name=yaah-agent"]


class LocalGit:
    """GitPort via the system `git` binary.

    `mode='worktree'` adds a worktree off a local repo (local profile).
    `mode='clone'` (remote profile) clones the repo ONCE into a local cache
    (`~/.yaah/cache/<repo>`) and then `git worktree add`s per run off that cache —
    one network clone, with every run worktree-based like the local profile.
    """

    def __init__(self, *, cache_root: str | Path | None = None) -> None:
        # Absolute, outside any repo. Remote repos are cloned ONCE here, then
        # worktreed per run.
        self._cache_root = (
            Path(cache_root).resolve() if cache_root
            else Path.home() / ".yaah" / "cache"
        )

    def _cache_dir(self, repo_ref: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9]+", "-", repo_ref).strip("-")[:60]
        digest = hashlib.sha1(repo_ref.encode()).hexdigest()[:8]
        return self._cache_root / f"{safe}-{digest}"

    def _ensure_cache(self, repo_ref: str, token: str | None) -> str:
        cache = self._cache_dir(repo_ref)
        if (cache / ".git").exists():
            self._run([*self._auth_args(token), "fetch", "origin"], cwd=str(cache))
        else:
            cache.parent.mkdir(parents=True, exist_ok=True)
            self._run([*self._auth_args(token), "clone", repo_ref, str(cache)])
        return str(cache)

    def _run(self, args: list[str], cwd: str | None = None, *, check: bool = True) -> str:
        proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
        if proc.returncode != 0 and check:
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
        base: str | None = None,
        token: str | None = None,
    ) -> None:
        if mode == "worktree":
            args = ["worktree", "add", "-b", branch, workspace_path]
            if base is not None:
                args.append(base)
            self._run(args, cwd=repo_ref)
        else:  # remote: clone once into a local cache, worktree per run off it
            cache = self._ensure_cache(repo_ref, token)
            baseref = f"origin/{base}" if base else "origin/HEAD"
            self._run([*_AUTHOR, "worktree", "add", "-b", branch, workspace_path, baseref],
                      cwd=cache)

    def commit_all(
        self, workspace_path: str, message: str, *, exclude: tuple[str, ...] = ()
    ) -> bool:
        # `:!<path>` pathspec magic excludes the scratch dirs from staging + status, so
        # they are neither committed nor counted as changes.
        pathspec = [".", *[f":!{e}" for e in exclude]]
        # --ignore-errors + check=False: an agent can leave a path git refuses to stage (a nested
        # repo with no commit, an explicitly-ignored path, etc.). Stage everything stageable and
        # commit that, rather than letting one bad path abort the whole run in open_pr.
        self._run(["add", "-A", "--ignore-errors", "--", *pathspec],
                  cwd=workspace_path, check=False)
        status = self._run(["status", "--porcelain", "--", *pathspec], cwd=workspace_path)
        if not status.strip():
            return False
        self._run([*_AUTHOR, "commit", "-m", message], cwd=workspace_path)
        return True

    def push(self, workspace_path: str, branch: str, *, token: str | None = None) -> None:
        self._run([*self._auth_args(token), "push", "origin", branch], cwd=workspace_path)

    def current_branch(self, workspace_path: str) -> str:
        return self._run(["rev-parse", "--abbrev-ref", "HEAD"], cwd=workspace_path).strip()

    def diff(self, workspace_path: str, *, paths: list[str]) -> str:
        return self._run(["diff", "--", *paths], cwd=workspace_path)

    def commit_to_branch(
        self, workspace_path: str, *, branch: str, base: str,
        paths: list[str], message: str,
    ) -> bool:
        # Create the memory branch off base, carrying the working-tree memory edits.
        self._run([*_AUTHOR, "checkout", "-b", branch, base], cwd=workspace_path)
        # Only stage paths that exist; memory paths like AGENTS.md may be absent.
        ws = Path(workspace_path)
        existing = [p for p in paths if (ws / p).exists()]
        if existing:
            self._run(["add", "--", *existing], cwd=workspace_path)
        status = self._run(["status", "--porcelain", "--", *paths], cwd=workspace_path)
        if not status.strip():
            return False
        self._run([*_AUTHOR, "commit", "-m", message], cwd=workspace_path)
        return True

    def merge_into_base(
        self, repo_ref: str, *, branch: str, base: str, token: str | None = None
    ) -> bool:
        # Fast-forward base to branch when branch is a descendant of base.
        base_sha = self._run(["rev-parse", base], cwd=repo_ref).strip()
        branch_sha = self._run(["rev-parse", branch], cwd=repo_ref).strip()
        if base_sha == branch_sha:
            return True
        merge_base = self._run(["merge-base", base, branch], cwd=repo_ref).strip()
        if merge_base != base_sha:
            raise GitError(f"{base} has diverged from {branch}; manual merge required")
        # ff: point the base ref at the branch tip (compare-and-swap on the old sha).
        self._run(["update-ref", f"refs/heads/{base}", branch_sha, base_sha], cwd=repo_ref)
        return True

    def merge_branch(self, workspace_path: str, *, branch: str) -> MergeResult:
        # Use subprocess directly (not _run): _run raises on non-zero, but here a
        # non-zero exit is the signal we need to distinguish a content conflict from
        # a precondition failure.
        proc = subprocess.run(
            ["git", *_AUTHOR, "merge", "--no-ff", "-m", f"merge {branch}", branch],
            cwd=workspace_path, capture_output=True, text=True,
        )
        if proc.returncode == 0:
            return MergeResult(ok=True, branch=branch)
        merging = subprocess.run(
            ["git", "-C", workspace_path, "rev-parse", "-q", "--verify", "MERGE_HEAD"],
            capture_output=True,
        ).returncode == 0
        if not merging:
            # The merge never started (nonexistent branch, dirty tree, in-progress
            # merge) — a precondition error, not a content conflict. Surface the real
            # cause instead of masking it with a `merge --abort` that itself fails.
            raise GitError(proc.stderr.strip() or f"git merge {branch} failed")
        files = self._run(["diff", "--name-only", "--diff-filter=U"], cwd=workspace_path)
        self._run(["merge", "--abort"], cwd=workspace_path)
        return MergeResult(ok=False, branch=branch,
                           conflict_files=[f for f in files.splitlines() if f.strip()])

    def has_commits_ahead(self, workspace_path: str, base: str) -> bool:
        out = self._run(["rev-list", "--count", f"{base}..HEAD"], cwd=workspace_path)
        return int(out.strip() or "0") > 0
