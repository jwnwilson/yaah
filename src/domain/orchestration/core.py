"""Pure orchestration policy: lead-decision/worker DTOs, guards, and mappings. No I/O."""

from collections import Counter
from enum import StrEnum
from typing import Literal

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
    memory_scope: Literal["project", "all"] = "project"


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
        if self.intent == OrchestrationIntent.NEEDS_HUMAN:
            has_user_message = any(
                m.recipient_kind == MessageRecipientKind.USER for m in self.messages
            )
            if not self.rationale.strip() and not has_user_message:
                raise ValueError("needs_human requires a rationale or a message to the user")
        return self


class AgentOutcome(StrEnum):
    OK = "ok"
    FAIL = "fail"
    BLOCKED = "blocked"


class AgentStepResult(BaseModel):
    """One worker turn's result (returned by the agent_step activity in Plan 3)."""

    outcome: AgentOutcome = AgentOutcome.OK
    completed_brief: bool = False
    outgoing: list[OutboundMessage] = Field(default_factory=list)
    artifacts: dict[str, str] = Field(default_factory=dict)
    cost_usd: float = 0.0


class MergeResult(BaseModel):
    """Outcome of merging one branch into the current worktree branch."""

    ok: bool
    branch: str = ""
    conflict_files: list[str] = Field(default_factory=list)


class AgentReport(BaseModel):
    """A worker's report back to the lead, summarized into orchestration state."""

    role: AgentRole
    outcome: AgentOutcome
    summary: str = ""
    cost_usd: float = 0.0


class MonitorVerdict(BaseModel):
    """The process monitor's completion check."""

    complete: bool
    unmet: list[str] = Field(default_factory=list)
    pending_mailboxes: list[str] = Field(default_factory=list)
    notes: str = ""


class OrchestrationLimits(BaseModel):
    """Anti-runaway bounds enforced by the workflow."""

    max_waves: int = 8
    max_dispatches: int = 20
    max_messages: int = 200
    max_cost_usd: float = 25.0
    max_verify_rounds: int = 3
    max_parallel_per_role: int = 3
    max_integration_rounds: int = 3


class OrchestrationState(BaseModel):
    """Immutable snapshot of a run's orchestration progress, fed to invoke_lead."""

    waves: int = 0
    total_dispatches: int = 0
    messages_sent: int = 0
    total_cost_usd: float = 0.0
    reports: list[AgentReport] = Field(default_factory=list)
    verdicts: list[MonitorVerdict] = Field(default_factory=list)
    last_integration: dict | None = None

    def record_wave(
        self, *, dispatch_count: int, messages: int, cost: float
    ) -> "OrchestrationState":
        return self.model_copy(
            update={
                "waves": self.waves + 1,
                "total_dispatches": self.total_dispatches + dispatch_count,
                "messages_sent": self.messages_sent + messages,
                "total_cost_usd": self.total_cost_usd + cost,
            }
        )

    def record_report(self, report: AgentReport) -> "OrchestrationState":
        return self.model_copy(update={"reports": [*self.reports, report]})

    def record_verdict(self, verdict: MonitorVerdict) -> "OrchestrationState":
        return self.model_copy(update={"verdicts": [*self.verdicts, verdict]})

    def record_integration(self, conflict: dict | None) -> "OrchestrationState":
        return self.model_copy(update={"last_integration": conflict})


def guard_exceeded(state: OrchestrationState, limits: OrchestrationLimits) -> str | None:
    """Return the name of the first exceeded limit, or None. Used to force a BLOCK.

    Limits are hard caps: reaching the limit blocks further work (>=).
    """
    if state.waves >= limits.max_waves:
        return "max_waves"
    if state.total_dispatches >= limits.max_dispatches:
        return "max_dispatches"
    if state.messages_sent >= limits.max_messages:
        return "max_messages"
    if state.total_cost_usd >= limits.max_cost_usd:
        return "max_cost_usd"
    return None


def wave_exceeds_parallel(target_roles: list[str], limits: OrchestrationLimits) -> bool:
    """True if any single role is dispatched more than max_parallel_per_role times in one wave."""
    counts = Counter(target_roles)
    return any(n > limits.max_parallel_per_role for n in counts.values())


def is_quiescent(active_agents: int, in_flight_messages: int) -> bool:
    """The system is quiescent when no agent is working and no message is in flight."""
    return active_agents == 0 and in_flight_messages == 0


def decision_to_messages(
    decision: OrchestrationDecision,
    *,
    owner_id: str,
    lead_agent_id: str,
    run_id: str,
    work_item_id: str | None,
    project_id: str | None,
    role_to_agent_id: dict[AgentRole, str],
) -> list[Message]:
    """Turn a lead decision's dispatches + notes into persistable Message rows.
    Dispatches/notes addressed to roles not on the team are skipped (nothing to deliver)."""
    out: list[Message] = []
    ctx = dict(owner_id=owner_id, run_id=run_id, work_item_id=work_item_id, project_id=project_id)
    for d in decision.dispatches:
        agent_id = role_to_agent_id.get(d.target_role)
        if agent_id is None:
            continue
        out.append(
            Message(
                sender_kind=MessageSenderKind.AGENT,
                sender_agent_id=lead_agent_id,
                recipient_kind=MessageRecipientKind.AGENT,
                recipient_agent_id=agent_id,
                kind=MessageKind.DISPATCH,
                body=d.instructions,
                **ctx,
            )
        )
    for m in decision.messages:
        recipient_agent_id = None
        if m.recipient_kind == MessageRecipientKind.AGENT:
            recipient_agent_id = (
                role_to_agent_id.get(m.recipient_role) if m.recipient_role else None
            )
            if recipient_agent_id is None:
                continue
        out.append(
            Message(
                sender_kind=MessageSenderKind.AGENT,
                sender_agent_id=lead_agent_id,
                recipient_kind=m.recipient_kind,
                recipient_agent_id=recipient_agent_id,
                kind=m.kind,
                subject=m.subject,
                body=m.body,
                **ctx,
            )
        )
    return out


def resolve_assignee(
    decision: OrchestrationDecision, role_to_agent_id: dict[AgentRole, str]
) -> str | None:
    """Map the lead's assignee_role to a team agent id, or None."""
    if decision.assignee_role is None:
        return None
    return role_to_agent_id.get(decision.assignee_role)
