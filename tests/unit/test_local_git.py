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


def test_commit_all_excludes_nested_engineer_worktree():
    # Reproduces the parallel-engineers pollution bug: per-engineer worktrees nest under
    # the run workspace (`.yaah-eng/...`), and open_pr's commit_all over the main worktree
    # would otherwise record them as gitlinks on the task branch. WORKSPACE_SCRATCH must
    # exclude `.yaah-eng`. Real git is required — fakes can't create nested worktrees.
    from domain.scm import WORKSPACE_SCRATCH

    bare = _bare_repo_with_commit()
    g = LocalGit()
    main_ws = tempfile.mkdtemp()
    g.prepare(repo_ref=bare, workspace_path=main_ws, branch="agent/t1", mode="clone")
    eng_ws = str(Path(main_ws) / ".yaah-eng" / "backend-1-0")
    g.prepare(repo_ref=main_ws, workspace_path=eng_ws,
              branch="agent/t1__backend-1-0", mode="worktree", base="agent/t1")
    _commit_file(g, eng_ws, "api.txt", "api", "eng work")  # nested worktree gets a HEAD
    (Path(main_ws) / "real.txt").write_text("integrated work")
    assert g.commit_all(main_ws, "open pr", exclude=WORKSPACE_SCRATCH) is True
    tracked = subprocess.run(["git", "-C", main_ws, "ls-tree", "-r", "--name-only", "HEAD"],
                             capture_output=True, text=True, check=True).stdout
    assert "real.txt" in tracked
    assert ".yaah-eng" not in tracked  # nested engineer worktree NOT committed as a gitlink


def test_curate_after_pr_keeps_memory_out_of_work_branch():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        _init_repo(ws)                                   # repo on main with an initial commit
        # seed a tracked CLAUDE.md (so the curator's change is a modify, like a real repo)
        (ws / "CLAUDE.md").write_text("# Project\n")
        subprocess.run(["git", "-C", str(ws), "add", "CLAUDE.md"], check=True,
                       capture_output=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(ws),
                        "commit", "-m", "add project memory"], check=True, capture_output=True)
        git = LocalGit()
        # 1) open_pr: the agent's work is committed to the task branch
        subprocess.run(["git", "-C", str(ws), "checkout", "-b", "agent/t1"], check=True,
                       capture_output=True)
        (ws / "feature.py").write_text("print('hi')\n")
        assert git.commit_all(str(ws), "work") is True
        # 2) curator edits project memory AFTER the work commit (uncommitted working tree)
        (ws / "CLAUDE.md").write_text("# Project\n- learned: pin deps\n")
        # 3) capture_memory: commit ONLY the memory paths to a separate branch off the work branch
        assert git.commit_to_branch(str(ws), branch="agent/memory-r1", base="agent/t1",
                                    paths=["CLAUDE.md", "AGENTS.md", "docs/adr"],
                                    message="memory update") is True
        # work branch (agent/t1) has the work but NOT the curator's CLAUDE.md edit
        work_claude = subprocess.run(["git", "-C", str(ws), "show", "agent/t1:CLAUDE.md"],
                                     capture_output=True, text=True).stdout
        assert "learned: pin deps" not in work_claude
        work_files = subprocess.run(["git", "-C", str(ws), "ls-tree", "-r", "--name-only",
                                     "agent/t1"], capture_output=True, text=True).stdout
        assert "feature.py" in work_files
        # memory branch HAS the curator's edit
        mem_claude = subprocess.run(["git", "-C", str(ws), "show", "agent/memory-r1:CLAUDE.md"],
                                    capture_output=True, text=True).stdout
        assert "learned: pin deps" in mem_claude


def test_commit_all_commits_work_despite_unstageable_path():
    # An agent can leave a path git refuses to stage (here: a nested git repo with no commit,
    # which makes `git add` abort with exit 128). open_pr's commit_all must not fail the whole
    # run over it — it should stage the legitimate work and commit that.
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        _init_repo(ws)
        nested = ws / "data" / "workspaces"
        nested.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "."], cwd=nested, check=True, capture_output=True)
        (ws / "feature.py").write_text("print('hi')\n")  # the legitimate work
        committed = LocalGit().commit_all(str(ws), "work", exclude=(".claude", ".orchestration"))
        assert committed is True
        files = subprocess.run(
            ["git", "-C", str(ws), "show", "--name-only", "--pretty=format:", "HEAD"],
            capture_output=True, text=True).stdout
        assert "feature.py" in files
