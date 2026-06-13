import subprocess
import tempfile
from pathlib import Path

from adapters.git.local_git import LocalGit


def _bare_repo_with_commit() -> str:
    bare = tempfile.mkdtemp(suffix=".git")
    subprocess.run(["git", "init", "--bare", "-b", "main", bare], check=True)
    # seed one commit via a temp clone
    seed = tempfile.mkdtemp()
    subprocess.run(["git", "clone", bare, seed], check=True)
    (Path(seed) / "README.md").write_text("hi")
    subprocess.run(["git", "-C", seed, "add", "."], check=True)
    subprocess.run(
        ["git", "-C", seed, "-c", "user.email=a@b.c", "-c", "user.name=t", "commit", "-m", "init"],
        check=True,
    )
    subprocess.run(["git", "-C", seed, "push", "origin", "main"], check=True)
    return bare


def test_clone_commit_push_roundtrip():
    bare = _bare_repo_with_commit()
    ws = tempfile.mkdtemp()
    g = LocalGit()
    g.prepare(repo_ref=bare, workspace_path=ws, branch="agent/t1", mode="clone")
    assert g.current_branch(ws) == "agent/t1"
    (Path(ws) / "new.txt").write_text("work")
    assert g.commit_all(ws, "add new") is True
    g.push(ws, "agent/t1")
    # branch now exists on the bare remote
    out = subprocess.run(
        ["git", "-C", bare, "branch", "--list", "agent/t1"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "agent/t1" in out.stdout


def test_commit_all_false_when_no_changes():
    bare = _bare_repo_with_commit()
    ws = tempfile.mkdtemp()
    g = LocalGit()
    g.prepare(repo_ref=bare, workspace_path=ws, branch="agent/t2", mode="clone")
    assert g.commit_all(ws, "noop") is False
