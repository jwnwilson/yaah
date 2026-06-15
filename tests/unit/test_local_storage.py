import tempfile

from adapters.storage.local import LocalStorageAdapter


def test_write_read_exists_delete():
    s = LocalStorageAdapter(base_dir=tempfile.mkdtemp())
    s.write_bytes("runs/r1/plan.md", b"hello")
    assert s.exists("runs/r1/plan.md")
    assert s.read_text("runs/r1/plan.md") == "hello"
    s.delete("runs/r1/plan.md")
    assert not s.exists("runs/r1/plan.md")
    assert s.read_text("missing") == ""


def test_local_path_creates_dir_and_delete_directory():
    s = LocalStorageAdapter(base_dir=tempfile.mkdtemp())
    p = s.local_path("runs/r1")
    import os
    assert os.path.isdir(p)
    s.write_bytes("runs/r1/a.txt", b"x")
    s.delete_directory("runs/r1/")
    assert not s.exists("runs/r1")


def test_local_path_is_absolute_even_for_relative_base():
    # A workspace path is used as a process cwd and as the target of `git worktree add`
    # (run with cwd=<target repo>); a relative path would resolve against the wrong cwd,
    # splitting the agent's workspace from the provisioned worktree.
    import os
    s = LocalStorageAdapter(base_dir="data/workspaces")
    assert os.path.isabs(s.local_path("runs/r1"))
