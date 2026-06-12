from domain.workspace import Workspace


def test_workspace_dto():
    ws = Workspace(run_id="r1", path="/tmp/run-r1")
    assert ws.run_id == "r1" and ws.path == "/tmp/run-r1"
