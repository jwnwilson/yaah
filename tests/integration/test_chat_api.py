"""Integration tests for the synchronous refinement chat API (T5)."""
from fastapi.testclient import TestClient

from domain.projects import WorkItemKind
from domain.refinement import RefinementAction, RefinementOutput, WorkItemProposal
from interactors.api.app import create_app
from interactors.api.deps import refinement_agent, temporal_client
from interactors.api.settings import Settings


def _client():
    return TestClient(create_app(Settings(_env_file=None, database_url="sqlite:///:memory:")))


def _project(c) -> str:
    return c.post("/projects", json={"name": "Alpha", "repo_url": "r"}).json()["data"]["id"]


def test_chat_drafts_a_work_item():
    c = _client()
    pid = _project(c)
    r = c.post(f"/projects/{pid}/chat", json={"message": "build login"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["reply"] and data["session_id"]
    assert len(data["created_items"]) == 1
    item = data["created_items"][0]
    assert item["status"] == "draft" and item["kind"] == "epic"  # never ready
    # the draft is on the board
    items = c.get(f"/projects/{pid}/work-items", params={"kind": "epic"}).json()["data"]
    assert any(i["id"] == item["id"] for i in items)


def test_chat_history_round_trips():
    c = _client()
    pid = _project(c)
    sid = c.post(f"/projects/{pid}/chat", json={"message": "hi"}).json()["data"]["session_id"]
    msgs = c.get(f"/chat/{sid}/messages").json()["data"]
    roles = [m["role"] for m in msgs]
    assert "user" in roles and "assistant" in roles


def test_chat_continues_existing_session():
    c = _client()
    pid = _project(c)
    r1 = c.post(f"/projects/{pid}/chat", json={"message": "first"})
    sid = r1.json()["data"]["session_id"]
    r2 = c.post(f"/projects/{pid}/chat", json={"message": "second", "session_id": sid})
    assert r2.status_code == 200
    assert r2.json()["data"]["session_id"] == sid
    msgs = c.get(f"/chat/{sid}/messages").json()["data"]
    assert len(msgs) == 4  # user + assistant + user + assistant


def test_list_sessions_for_project():
    c = _client()
    pid = _project(c)
    c.post(f"/projects/{pid}/chat", json={"message": "a"})
    c.post(f"/projects/{pid}/chat", json={"message": "b"})
    r = c.get(f"/projects/{pid}/chat")
    assert r.status_code == 200
    sessions = r.json()["data"]
    assert len(sessions) == 2


def test_chat_unknown_project_returns_404():
    c = _client()
    r = c.post("/projects/doesnotexist/chat", json={"message": "hi"})
    assert r.status_code == 404


def test_items_always_created_as_draft():
    """Proposals must land as DRAFT regardless of FakeRefinementAgent output."""
    c = _client()
    pid = _project(c)
    r = c.post(f"/projects/{pid}/chat", json={"message": "anything"})
    for item in r.json()["data"]["created_items"]:
        assert item["status"] == "draft"


def _make_epic(c, pid) -> str:
    return c.post(
        f"/projects/{pid}/work-items", json={"kind": "epic", "title": "Checkout"}
    ).json()["data"]["id"]


def test_epic_scoped_chat_drafts_child_feature_and_returns_proposed_update():
    c = _client()
    pid = _project(c)
    epic_id = _make_epic(c, pid)
    r = c.post(f"/projects/{pid}/chat", json={"message": "cart flow", "epic_id": epic_id})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["proposed_epic_update"] is not None
    assert data["proposed_epic_update"]["body"]
    # the child feature was drafted under the epic
    assert data["created_items"][0]["kind"] == "feature"
    assert data["created_items"][0]["parent_id"] == epic_id


def test_unscoped_chat_has_no_proposed_epic_update():
    c = _client()
    pid = _project(c)
    data = c.post(f"/projects/{pid}/chat", json={"message": "build login"}).json()["data"]
    assert data["proposed_epic_update"] is None


def test_chat_proposes_edit_to_existing_item_without_applying():
    from domain.refinement import RefinementOutput, WorkItemEdit
    from interactors.api.deps import refinement_agent

    class _Editor:
        def respond(self, ctx):
            target = ctx.hierarchy[0]
            return RefinementOutput(
                reply="proposing edit",
                updates=[WorkItemEdit(id=target.id, body="NEW BODY", title="Renamed")],
            )

    app = create_app(Settings(_env_file=None, database_url="sqlite:///:memory:"))
    app.dependency_overrides[refinement_agent] = lambda: _Editor()
    c = TestClient(app)
    pid = c.post("/projects", json={"name": "Alpha", "repo_url": "r"}).json()["data"]["id"]
    epic_id = c.post(
        f"/projects/{pid}/work-items", json={"kind": "epic", "title": "E"}
    ).json()["data"]["id"]

    data = c.post(f"/projects/{pid}/chat", json={"message": "edit it"}).json()["data"]
    assert len(data["proposed_updates"]) == 1
    pu = data["proposed_updates"][0]
    assert pu["id"] == epic_id
    assert pu["body"] == "NEW BODY" and pu["title"] == "Renamed"
    assert pu["current_title"] == "E" and pu["kind"] == "epic"
    # proposed only — the item is unchanged until approved
    assert c.get(f"/work-items/{epic_id}").json()["data"]["body"] == ""
    assert c.get(f"/work-items/{epic_id}").json()["data"]["title"] == "E"


def test_chat_skips_edit_to_unknown_item():
    from domain.refinement import RefinementOutput, WorkItemEdit
    from interactors.api.deps import refinement_agent

    class _Editor:
        def respond(self, ctx):
            return RefinementOutput(reply="x", updates=[WorkItemEdit(id="nope", body="b")])

    app = create_app(Settings(_env_file=None, database_url="sqlite:///:memory:"))
    app.dependency_overrides[refinement_agent] = lambda: _Editor()
    c = TestClient(app)
    pid = c.post("/projects", json={"name": "A", "repo_url": "r"}).json()["data"]["id"]
    data = c.post(f"/projects/{pid}/chat", json={"message": "hi"}).json()["data"]
    assert data["proposed_updates"] == []
    assert "unknown item nope" in data["reply"]


class _FakeTemporal:
    def __init__(self):
        self.started = []

    def start_run_workflow(self, run_input, workflow_name="OrchestratorWorkflow"):
        self.started.append((workflow_name, run_input))

    def signal(self, run_id, name):  # pragma: no cover - unused
        pass


class _ScriptedAgent:
    """Turn 1: draft a task under the given parent. Turn 2+: commit."""

    def __init__(self, parent_id):
        self.parent_id = parent_id
        self.calls = 0

    def respond(self, ctx):
        self.calls += 1
        if self.calls == 1:
            return RefinementOutput(
                reply="drafted a task — confirm to start",
                proposals=[WorkItemProposal(kind=WorkItemKind.TASK,
                                            parent_id=self.parent_id, title="T")],
            )
        return RefinementOutput(reply="starting", action=RefinementAction.COMMIT)


def test_commit_starts_a_run_for_session_drafted_task():
    # One app/client throughout so the in-memory SQLite DB is shared across requests.
    # Build the app first so we can create the epic, THEN wire the scripted agent to it.
    app = create_app(Settings(_env_file=None, database_url="sqlite:///:memory:"))
    fake = _FakeTemporal()
    app.dependency_overrides[temporal_client] = lambda: fake
    c = TestClient(app)

    pid = c.post("/projects", json={"name": "p", "repo_url": "r"}).json()["data"]["id"]
    team_id = c.post("/teams/default").json()["data"]["team"]["id"]
    c.patch(f"/projects/{pid}", json={"team_id": team_id})
    epic = c.post(f"/projects/{pid}/work-items",
                  json={"kind": "epic", "title": "E"}).json()["data"]

    # One shared instance so `calls` increments across the two turns (turn 1 drafts,
    # turn 2 commits) — FastAPI does not memoize overrides across requests.
    scripted = _ScriptedAgent(epic["id"])
    app.dependency_overrides[refinement_agent] = lambda: scripted

    # Turn 1: draft a task (DRAFT, tagged with the session). No runs yet.
    r1 = c.post(f"/projects/{pid}/chat", json={"message": "break it down"}).json()["data"]
    sid = r1["session_id"]
    assert len(r1["created_items"]) == 1
    assert r1["created_items"][0]["status"] == "draft"
    assert fake.started == []

    # Turn 2: approve → commit. Task promoted to READY, epic activated, run started.
    r2 = c.post(f"/projects/{pid}/chat",
                json={"message": "go", "session_id": sid}).json()["data"]
    assert len(fake.started) == 1
    workflow_name, run_input = fake.started[0]
    assert workflow_name == "OrchestratorWorkflow"
    assert run_input["task_id"] == r1["created_items"][0]["id"]
    assert run_input["task_title"] == "T"
    assert r2["started_runs"] == [run_input["run_id"]]

    item = c.get(f"/work-items/{r1['created_items'][0]['id']}").json()["data"]
    assert item["status"] == "in_progress"


def test_commit_with_nothing_to_start_is_noop():
    app = create_app(Settings(_env_file=None, database_url="sqlite:///:memory:"))
    fake = _FakeTemporal()
    app.dependency_overrides[temporal_client] = lambda: fake

    class _CommitOnly:
        def respond(self, ctx):
            return RefinementOutput(reply="ok", action=RefinementAction.COMMIT)

    app.dependency_overrides[refinement_agent] = lambda: _CommitOnly()
    c = TestClient(app)
    pid = c.post("/projects", json={"name": "p", "repo_url": "r"}).json()["data"]["id"]

    r = c.post(f"/projects/{pid}/chat", json={"message": "go"})
    assert r.status_code == 200
    assert r.json()["data"]["started_runs"] == []
    assert fake.started == []


def test_commit_turn_does_not_start_same_turn_proposals():
    app = create_app(Settings(_env_file=None, database_url="sqlite:///:memory:"))
    fake = _FakeTemporal()
    app.dependency_overrides[temporal_client] = lambda: fake
    c = TestClient(app)

    pid = c.post("/projects", json={"name": "p", "repo_url": "r"}).json()["data"]["id"]
    team_id = c.post("/teams/default").json()["data"]["team"]["id"]
    c.patch(f"/projects/{pid}", json={"team_id": team_id})
    epic = c.post(f"/projects/{pid}/work-items",
                  json={"kind": "epic", "title": "E"}).json()["data"]

    class _ProposeAndCommit:
        def respond(self, ctx):
            return RefinementOutput(
                reply="here and starting",
                proposals=[WorkItemProposal(kind=WorkItemKind.TASK,
                                            parent_id=epic["id"], title="T")],
                action=RefinementAction.COMMIT,
            )

    app.dependency_overrides[refinement_agent] = lambda: _ProposeAndCommit()
    data = c.post(f"/projects/{pid}/chat", json={"message": "go"}).json()["data"]

    # The task was drafted this turn, so it must NOT be promoted/started.
    assert data["started_runs"] == []
    assert fake.started == []
    assert data["created_items"][0]["status"] == "draft"
