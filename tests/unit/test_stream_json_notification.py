import json

from adapters.agent.runtime import stream_json
from domain.models import RunStage


def test_yaah_notify_tool_use_becomes_notification_event():
    line = json.dumps({
        "type": "assistant",
        "message": {"content": [
            {"type": "text", "text": "I'll flag this."},
            {"type": "tool_use", "name": "yaah_notify",
             "input": {"category": "decision", "title": "DB choice",
                       "body": "Postgres over SQLite", "severity": "info"}},
        ]},
    })
    events, _result = stream_json.parse([line], RunStage.IMPLEMENT)
    notifs = [e for e in events if e.type == "notification"]
    assert len(notifs) == 1
    assert notifs[0].data["title"] == "DB choice"
    assert notifs[0].message == "DB choice"


def test_malformed_yaah_notify_missing_title_is_dropped():
    line = json.dumps({
        "type": "assistant",
        "message": {"content": [
            {"type": "tool_use", "name": "yaah_notify", "input": {"category": "decision"}},
        ]},
    })
    events, _result = stream_json.parse([line], RunStage.IMPLEMENT)
    assert [e for e in events if e.type == "notification"] == []


def test_other_tool_use_is_ignored():
    line = json.dumps({
        "type": "assistant",
        "message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
        ]},
    })
    events, _result = stream_json.parse([line], RunStage.IMPLEMENT)
    assert [e for e in events if e.type == "notification"] == []
