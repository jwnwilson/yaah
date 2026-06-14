from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings


def _client() -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, database_url="sqlite:///:memory:")))


def _send(c, **over):
    body = {"recipient_kind": "agent", "recipient_agent_id": "a-eng", "body": "hi"}
    body.update(over)
    return c.post("/messages", json=body)


def test_send_and_list_message_to_agent_mailbox():
    c = _client()
    r = _send(c, body="please build")
    assert r.status_code == 201
    listed = c.get("/messages", params={"box": "a-eng"}).json()["data"]
    assert len(listed) == 1 and listed[0]["body"] == "please build"
    assert listed[0]["sender_kind"] == "user"


def test_unread_count_and_mark_read():
    c = _client()
    mid = _send(c).json()["data"]["id"]
    assert c.get("/messages/unread-count", params={"box": "a-eng"}).json()["data"]["count"] == 1
    c.patch(f"/messages/{mid}", json={"read": True})
    assert c.get("/messages/unread-count", params={"box": "a-eng"}).json()["data"]["count"] == 0
    read = c.get("/messages", params={"box": "a-eng", "status": "read"}).json()["data"]
    assert len(read) == 1 and read[0]["read_at"] is not None


def test_me_mailbox_holds_user_recipient_messages():
    c = _client()
    c.post("/messages", json={"recipient_kind": "user", "body": "note to self"})
    me = c.get("/messages", params={"box": "me"}).json()["data"]
    assert len(me) == 1 and me[0]["recipient_kind"] == "user"


def test_patch_work_item_sets_assignee():
    c = _client()
    pid = c.post("/projects", json={"name": "p", "repo_url": "r"}).json()["data"]["id"]
    epic = c.post(f"/projects/{pid}/work-items",
                  json={"kind": "epic", "title": "E"}).json()["data"]
    c.patch(f"/work-items/{epic['id']}", json={"assignee_agent_id": "a-eng"})
    got = c.get(f"/work-items/{epic['id']}").json()["data"]
    assert got["assignee_agent_id"] == "a-eng"


def test_list_messages_by_sender_shows_agent_output():
    from adapters.database.uow import SqlUnitOfWork
    from domain.models import Message, MessageKind, MessageRecipientKind, MessageSenderKind

    c = _client()
    uow = SqlUnitOfWork(c.app.state.session_factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        uow.messages.create(Message(
            owner_id="dev-user", sender_kind=MessageSenderKind.AGENT, sender_agent_id="a-lead",
            recipient_kind=MessageRecipientKind.AGENT, recipient_agent_id="a-eng",
            kind=MessageKind.DISPATCH, body="build the widget", run_id="r1",
        ))
    sent = c.get("/messages", params={"sender": "a-lead"}).json()["data"]
    assert len(sent) == 1 and sent[0]["body"] == "build the widget"
    assert c.get("/messages", params={"sender": "nobody"}).json()["data"] == []
