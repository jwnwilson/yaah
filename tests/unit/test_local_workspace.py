import os

from adapters.workspace.local import LocalTempWorkspace


def test_provision_creates_dir_and_destroy_removes_it():
    provider = LocalTempWorkspace()
    ws = provider.provision("r1")
    assert os.path.isdir(ws.path)
    provider.destroy(ws)
    assert not os.path.exists(ws.path)
