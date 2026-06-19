"""Message entity: the inter-agent / agent-user mailbox substrate."""
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from domain.base import new_id, utc_now
from domain.runs import Run, RunEvent, RunEventType


class MessageSenderKind(StrEnum):
    AGENT = "agent"
    SYSTEM = "system"
    USER = "user"


class MessageRecipientKind(StrEnum):
    AGENT = "agent"
    USER = "user"


class MessageKind(StrEnum):
    DISPATCH = "dispatch"   # lead -> worker work assignment
    REPORT = "report"       # worker -> lead result
    CHAT = "chat"           # peer-to-peer
    STATUS = "status"       # progress note
    NOTICE = "notice"       # informational system/agent notice
    GATE = "gate"           # action-required gate-approval notice (deep-links to the run)


class MessageSeverity(StrEnum):
    INFO = "info"
    ATTENTION = "attention"
    CRITICAL = "critical"


class Message(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    sender_kind: MessageSenderKind
    sender_agent_id: str | None = None
    recipient_kind: MessageRecipientKind
    recipient_agent_id: str | None = None
    kind: MessageKind = MessageKind.CHAT
    severity: MessageSeverity = MessageSeverity.INFO
    subject: str = ""
    body: str = ""
    run_id: str | None = None
    work_item_id: str | None = None
    project_id: str | None = None
    delivered_at: datetime | None = None
    processed_at: datetime | None = None
    read_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _identity_rules(self) -> "Message":
        if self.sender_kind == MessageSenderKind.AGENT and not self.sender_agent_id:
            raise ValueError("agent sender requires sender_agent_id")
        if self.recipient_kind == MessageRecipientKind.AGENT and not self.recipient_agent_id:
            raise ValueError("agent recipient requires recipient_agent_id")
        if self.sender_kind != MessageSenderKind.AGENT and self.sender_agent_id is not None:
            raise ValueError("non-agent sender must not carry sender_agent_id")
        if (
            self.recipient_kind != MessageRecipientKind.AGENT
            and self.recipient_agent_id is not None
        ):
            raise ValueError("non-agent recipient must not carry recipient_agent_id")
        return self


def message_for_event(ev: RunEvent, *, run: Run) -> Message | None:
    """Map a structural run event to a user-recipient system message, or None if it
    isn't user-facing. Pure: never raises on unmapped types."""
    common = dict(
        owner_id=run.owner_id,
        sender_kind=MessageSenderKind.SYSTEM,
        recipient_kind=MessageRecipientKind.USER,
        run_id=run.id,
        work_item_id=run.task_id,
    )
    if ev.type == RunEventType.GATE_OPENED:
        return Message(
            kind=MessageKind.GATE,
            severity=MessageSeverity.ATTENTION,
            subject="Approval needed",
            body=f"A run reached the {ev.stage} gate and needs your approval.",
            **common,
        )
    if ev.type == RunEventType.BLOCKED:
        return Message(
            kind=MessageKind.NOTICE,
            severity=MessageSeverity.ATTENTION,
            subject="Run blocked",
            body=ev.message or f"A run blocked at {ev.stage}.",
            **common,
        )
    if ev.type == RunEventType.ERROR:
        return Message(
            kind=MessageKind.NOTICE,
            severity=MessageSeverity.CRITICAL,
            subject="Run failed",
            body=ev.message or f"A run errored at {ev.stage}.",
            **common,
        )
    return None


def message_resolves(msg: Message, ev: RunEvent) -> bool:
    """True when this event resolves the (action-required) gate message."""
    return (
        ev.type == RunEventType.GATE_RESOLVED
        and msg.kind == MessageKind.GATE
        and msg.run_id == ev.run_id
    )
