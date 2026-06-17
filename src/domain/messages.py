"""Message entity: the inter-agent / agent-user mailbox substrate."""
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from domain.base import new_id, utc_now


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


class Message(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    sender_kind: MessageSenderKind
    sender_agent_id: str | None = None
    recipient_kind: MessageRecipientKind
    recipient_agent_id: str | None = None
    kind: MessageKind = MessageKind.CHAT
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
