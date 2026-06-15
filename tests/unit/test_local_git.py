import subprocess
import tempfile
from pathlib import Path

import pytest

from adapters.git.local_git import GitError, LocalGit


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


def test_commit_all_excludes_scratch_dirs():
    bare = _bare_repo_with_commit()
    ws = tempfile.mkdtemp()
    g = LocalGit()
    g.prepare(repo_ref=bare, workspace_path=ws, branch="agent/t3", mode="clone")
    (Path(ws) / "WELCOME.md").write_text("hi")  # real work
    (Path(ws) / ".orchestration").mkdir()
    (Path(ws) / ".orchestration" / "decision.json").write_text("{}")  # scratch
    (Path(ws) / ".claude").mkdir()
    (Path(ws) / ".claude" / "settings.json").write_text("{}")  # scratch
    assert g.commit_all(ws, "work", exclude=(".claude", ".orchestration")) is True
    tracked = subprocess.run(
        ["git", "-C", ws, "ls-tree", "-r", "--name-only", "HEAD"],
        capture_output=True, text=True, check=True).stdout
    assert "WELCOME.md" in tracked
    assert ".orchestration" not in tracked and ".claude" not in tracked


def test_commit_all_false_when_only_scratch_changes():
    bare = _bare_repo_with_commit()
    ws = tempfile.mkdtemp()
    g = LocalGit()
    g.prepare(repo_ref=bare, workspace_path=ws, branch="agent/t4", mode="clone")
    (Path(ws) / ".orchestration").mkdir()
    (Path(ws) / ".orchestration" / "decision.json").write_text("{}")
    assert g.commit_all(ws, "scratch only", exclude=(".claude", ".orchestration")) is False


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True,
                   capture_output=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "--allow-empty", "-m", "init"], cwd=path, check=True,
                   capture_output=True)
    (path / "CLAUDE.md").write_text("# original\n")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-m", "add memory"], cwd=path, check=True,
                   capture_output=True)


def test_diff_shows_working_tree_memory_change():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        _init_repo(ws)
        (ws / "CLAUDE.md").write_text("# original\n# learned\n")
        out = LocalGit().diff(str(ws), paths=["CLAUDE.md", "AGENTS.md", "docs/adr"])
        assert "learned" in out
        assert "CLAUDE.md" in out


def test_commit_to_branch_commits_only_memory_paths():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        _init_repo(ws)
        (ws / "CLAUDE.md").write_text("# original\n# learned\n")
        (ws / "other.py").write_text("print('x')\n")  # non-memory change
        git = LocalGit()
        committed = git.commit_to_branch(str(ws), branch="agent/memory-r1", base="main",
                                         paths=["CLAUDE.md", "AGENTS.md", "docs/adr"],
                                         message="memory update")
        assert committed is True
        assert git.current_branch(str(ws)) == "agent/memory-r1"
        # the memory commit contains CLAUDE.md, not other.py
        files = subprocess.run(["git", "show", "--name-only", "--pretty=format:"],
                               cwd=ws, capture_output=True, text=True).stdout
        assert "CLAUDE.md" in files
        assert "other.py" not in files


def test_commit_to_branch_returns_false_with_no_memory_changes():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        _init_repo(ws)
        committed = LocalGit().commit_to_branch(str(ws), branch="b", base="main",
                                                paths=["CLAUDE.md"], message="m")
        assert committed is False


def test_merge_into_base_fast_forwards_base_to_branch():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        _init_repo(ws)
        # Create a memory branch off main with an extra commit, then return main to HEAD.
        (ws / "CLAUDE.md").write_text("# original\n# learned\n")
        git = LocalGit()
        git.commit_to_branch(str(ws), branch="agent/memory-r1", base="main",
                             paths=["CLAUDE.md"], message="memory update")
        # base (main) does not yet contain the memory commit.
        before = subprocess.run(["git", "log", "main", "--oneline"],
                                cwd=ws, capture_output=True, text=True).stdout
        assert "memory update" not in before
        # Act
        assert git.merge_into_base(str(ws), branch="agent/memory-r1", base="main") is True
        # Assert main now contains the memory commit.
        after = subprocess.run(["git", "log", "main", "--oneline"],
                               cwd=ws, capture_output=True, text=True).stdout
        assert "memory update" in after


def test_merge_into_base_noop_when_branch_equals_base():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        _init_repo(ws)
        assert LocalGit().merge_into_base(str(ws), branch="main", base="main") is True


def test_prepare_worktree_branches_off_base():
    bare = _bare_repo_with_commit()
    g = LocalGit()
    base_ws = tempfile.mkdtemp()
    g.prepare(repo_ref=bare, workspace_path=base_ws, branch="agent/t1", mode="clone")
    (Path(base_ws) / "base.txt").write_text("on task branch")
    assert g.commit_all(base_ws, "task work") is True
    g.push(base_ws, "agent/t1")
    eng_ws = tempfile.mkdtemp()
    g.prepare(repo_ref=base_ws, workspace_path=eng_ws,
              branch="agent/t1__backend-1-0", mode="worktree", base="agent/t1")
    assert (Path(eng_ws) / "base.txt").exists()
    assert g.current_branch(eng_ws) == "agent/t1__backend-1-0"


def _commit_file(g, ws, name, content, msg):
    (Path(ws) / name).write_text(content)
    assert g.commit_all(ws, msg) is True


def test_merge_branch_fast_forward_and_ahead():
    bare = _bare_repo_with_commit()
    g = LocalGit()
    main_ws = tempfile.mkdtemp()
    g.prepare(repo_ref=bare, workspace_path=main_ws, branch="agent/t1", mode="clone")
    assert g.has_commits_ahead(main_ws, "main") is False
    eng_ws = tempfile.mkdtemp()
    g.prepare(repo_ref=main_ws, workspace_path=eng_ws,
              branch="agent/t1__e0", mode="worktree", base="agent/t1")
    _commit_file(g, eng_ws, "a.txt", "A", "eng work")
    res = g.merge_branch(main_ws, branch="agent/t1__e0")
    assert res.ok is True and res.conflict_files == []
    assert (Path(main_ws) / "a.txt").exists()
    assert g.has_commits_ahead(main_ws, "main") is True


def test_merge_branch_conflict_aborts_clean():
    bare = _bare_repo_with_commit()
    g = LocalGit()
    main_ws = tempfile.mkdtemp()
    g.prepare(repo_ref=bare, workspace_path=main_ws, branch="agent/t1", mode="clone")
    eng_ws = tempfile.mkdtemp()
    g.prepare(repo_ref=main_ws, workspace_path=eng_ws,
              branch="agent/t1__e0", mode="worktree", base="agent/t1")
    # Diverge: eng and main each touch c.txt independently off the same base.
    _commit_file(g, eng_ws, "c.txt", "from-eng", "eng change")
    _commit_file(g, main_ws, "c.txt", "from-main", "main change")
    res = g.merge_branch(main_ws, branch="agent/t1__e0")
    assert res.ok is False and "c.txt" in res.conflict_files
    import subprocess
    st = subprocess.run(["git", "-C", main_ws, "status", "--porcelain"],
                        capture_output=True, text=True).stdout
    assert "UU" not in st


def test_merge_branch_nonexistent_branch_raises():
    bare = _bare_repo_with_commit()
    g = LocalGit()
    main_ws = tempfile.mkdtemp()
    g.prepare(repo_ref=bare, workspace_path=main_ws, branch="agent/t1", mode="clone")
    # No merge ever starts (branch does not exist), so the real cause must surface
    # as a GitError rather than a masked `merge --abort` failure.
    with pytest.raises(GitError) as exc:
        g.merge_branch(main_ws, branch="agent/does-not-exist")
    # The real cause must surface, not a masked "no merge to abort" artifact from an
    # unconditional `merge --abort` on a merge that never started.
    assert "MERGE_HEAD missing" not in str(exc.value)
