"""Pure orchestration policy: lead-decision/worker DTOs, guards, and mappings. No I/O."""

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from domain.models import (
    AgentRole,
    Message,
    MessageKind,
    MessageRecipientKind,
    MessageSenderKind,
)


class OrchestrationIntent(StrEnum):
    CONTINUE = "continue"       # run the dispatches, then re-invoke the lead
    VERIFY = "verify"           # trigger the completion monitor
    COMPLETE = "complete"       # honored only after a monitor pass
    BLOCK = "block"             # give up with a reason
    NEEDS_HUMAN = "needs_human"  # open a human gate


class Dispatch(BaseModel):
    """The lead's 'trigger an agent' unit."""

    target_role: AgentRole
    instructions: str
    acceptance: list[str] = Field(default_factory=list)


class OutboundMessage(BaseModel):
    """A message the lead or a worker wants sent. Agent recipients are addressed by
    role and resolved to an agent id by the caller."""

    recipient_kind: MessageRecipientKind
    recipient_role: AgentRole | None = None
    kind: MessageKind = MessageKind.CHAT
    subject: str = ""
    body: str

    @model_validator(mode="after")
    def _recipient_rules(self) -> "OutboundMessage":
        if self.recipient_kind == MessageRecipientKind.AGENT and self.recipient_role is None:
            raise ValueError("agent recipient requires recipient_role")
        return self


class OrchestrationDecision(BaseModel):
    """The lead's validated structured output for one invocation."""

    intent: OrchestrationIntent
    dispatches: list[Dispatch] = Field(default_factory=list)
    messages: list[OutboundMessage] = Field(default_factory=list)
    assignee_role: AgentRole | None = None
    rationale: str = ""

    @model_validator(mode="after")
    def _intent_rules(self) -> "OrchestrationDecision":
        if (
            self.intent == OrchestrationIntent.CONTINUE
            and not self.dispatches
            and not self.messages
        ):
            raise ValueError("continue requires at least one dispatch or message")
        if self.intent == OrchestrationIntent.BLOCK and not self.rationale.strip():
            raise ValueError("block requires a rationale")
        return self
