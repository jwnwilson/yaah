from domain.agent import AgentEvent
from domain.runs import RunStage


def test_agent_event_accepts_notification_type():
    ev = AgentEvent(type="notification", stage=RunStage.IMPLEMENT,
                    message="chose Postgres",
                    data={"category": "decision", "title": "DB choice",
                          "body": "Postgres over SQLite", "severity": "info"})
    assert ev.type == "notification"
    assert ev.data["category"] == "decision"
