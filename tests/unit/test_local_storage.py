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
