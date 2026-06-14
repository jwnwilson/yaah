# Orchestration Domain & Guards — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the pure-domain types, guard policy, mapping helpers, and lead-decision contract for lead-driven orchestration — everything the Temporal workflow/actors (Plan 3) will consume, with zero I/O.

**Architecture:** Two pure modules — `domain/orchestration.py` (DTOs, state, guards, quiescence, decision→Message/assignee mappings) and `domain/orchestration_prompts.py` (orchestrator prompt builder + decision/verdict parsing contract). Pydantic v2 models with validators; mirrors the existing `domain/capabilities.py` and `domain/prompts.py` style (pure policy, no adapter imports). Builds on Plan 1's `Message` model.

**Tech Stack:** Python 3.12, Pydantic v2, pytest (no DB, no Temporal — these are pure unit tests).

**Scope:** Plan 2 of 3 (see `docs/specs/2026-06-14-lead-orchestration-design.md` / ADR-0002). Plan 1 (Message + assignee substrate) is merged. Plan 3 wires these types into `RunWorkflow`/`AgentWorkflow` + activities. No Temporal, no persistence, no HTTP here.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `src/domain/orchestration.py` | Intent/outcome enums; `Dispatch`, `OutboundMessage`, `OrchestrationDecision`, `AgentStepResult`, `AgentReport`, `MonitorVerdict`, `OrchestrationState`, `OrchestrationLimits`; `guard_exceeded`, `is_quiescent`; `decision_to_messages`, `resolve_assignee` | Create |
| `src/domain/orchestration_prompts.py` | `build_orchestrator_prompt`, `parse_decision`, `parse_verdict`, `OrchestrationContractError` | Create |
| `tests/unit/test_orchestration.py` | DTO validation, guards, quiescence, state, mappings | Create |
| `tests/unit/test_orchestration_prompts.py` | Prompt content, decision/verdict parsing + errors | Create |

---

## Task 1: Decision types — `Dispatch`, `OutboundMessage`, `OrchestrationDecision`

**Files:**
- Create: `src/domain/orchestration.py`
- Test: `tests/unit/test_orchestration.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_orchestration.py
import pytest

from domain.models import AgentRole, MessageKind, MessageRecipientKind
from domain.orchestration import (
    Dispatch,
    OrchestrationDecision,
    OrchestrationIntent,
    OutboundMessage,
)


def test_continue_decision_with_dispatch_is_valid():
    d = OrchestrationDecision(
        intent=OrchestrationIntent.CONTINUE,
        dispatches=[Dispatch(target_role=AgentRole.BACKEND, instructions="implement X")],
        assignee_role=AgentRole.BACKEND,
    )
    assert d.dispatches[0].acceptance == []
    assert d.rationale == ""


def test_continue_requires_dispatch_or_message():
    with pytest.raises(ValueError, match="continue requires"):
        OrchestrationDecision(intent=OrchestrationIntent.CONTINUE)


def test_block_requires_rationale():
    with pytest.raises(ValueError, match="block requires"):
        OrchestrationDecision(intent=OrchestrationIntent.BLOCK)


def test_verify_and_complete_need_no_dispatches():
    assert OrchestrationDecision(intent=OrchestrationIntent.VERIFY).dispatches == []
    assert OrchestrationDecision(intent=OrchestrationIntent.COMPLETE).intent == (
        OrchestrationIntent.COMPLETE
    )


def test_outbound_agent_message_requires_recipient_role():
    with pytest.raises(ValueError, match="recipient_role"):
        OutboundMessage(recipient_kind=MessageRecipientKind.AGENT, body="hi")


def test_outbound_user_message_is_valid():
    m = OutboundMessage(recipient_kind=MessageRecipientKind.USER, body="status update")
    assert m.kind == MessageKind.CHAT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_orchestration.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'domain.orchestration'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/domain/orchestration.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_orchestration.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/domain/orchestration.py tests/unit/test_orchestration.py
git commit -m "feat: orchestration decision DTOs (Dispatch, OutboundMessage, OrchestrationDecision)"
```

---

## Task 2: Worker-result & monitor types

**Files:**
- Modify: `src/domain/orchestration.py` (append)
- Test: `tests/unit/test_orchestration.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_orchestration.py`:

```python
def test_agent_step_result_defaults():
    from domain.orchestration import AgentOutcome, AgentStepResult

    r = AgentStepResult()
    assert r.outcome == AgentOutcome.OK
    assert r.completed_brief is False
    assert r.outgoing == [] and r.artifacts == {} and r.cost_usd == 0.0


def test_agent_report_carries_outcome_and_cost():
    from domain.orchestration import AgentOutcome, AgentReport

    rep = AgentReport(role=AgentRole.QA, outcome=AgentOutcome.FAIL, summary="2 failing", cost_usd=0.5)
    assert rep.outcome == AgentOutcome.FAIL and rep.cost_usd == 0.5


def test_monitor_verdict_complete_and_incomplete():
    from domain.orchestration import MonitorVerdict

    ok = MonitorVerdict(complete=True)
    assert ok.unmet == [] and ok.pending_mailboxes == []
    bad = MonitorVerdict(complete=False, unmet=["no tests"], pending_mailboxes=["qa"])
    assert bad.unmet == ["no tests"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_orchestration.py -k "agent_step or agent_report or monitor" -v`
Expected: FAIL — `ImportError: cannot import name 'AgentStepResult'`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/domain/orchestration.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_orchestration.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add src/domain/orchestration.py tests/unit/test_orchestration.py
git commit -m "feat: worker-result and monitor-verdict orchestration types"
```

---

## Task 3: Orchestration state, limits, guards & quiescence

**Files:**
- Modify: `src/domain/orchestration.py` (append)
- Test: `tests/unit/test_orchestration.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_orchestration.py`:

```python
def test_state_records_wave_report_and_cost_immutably():
    from domain.orchestration import AgentOutcome, AgentReport, OrchestrationState

    s0 = OrchestrationState()
    s1 = s0.record_wave(dispatch_count=2, messages=2, cost=1.5)
    s2 = s1.record_report(AgentReport(role=AgentRole.BACKEND, outcome=AgentOutcome.OK))
    assert s0.waves == 0 and s0.total_dispatches == 0          # original untouched
    assert s1.waves == 1 and s1.total_dispatches == 2 and s1.total_cost_usd == 1.5
    assert s2.reports[0].role == AgentRole.BACKEND


def test_guard_exceeded_flags_each_limit():
    from domain.orchestration import (
        OrchestrationLimits,
        OrchestrationState,
        guard_exceeded,
    )

    limits = OrchestrationLimits(max_waves=2, max_dispatches=3, max_messages=5, max_cost_usd=10.0)
    assert guard_exceeded(OrchestrationState(waves=2, total_dispatches=3), limits) is None
    assert guard_exceeded(OrchestrationState(waves=3), limits) == "max_waves"
    assert guard_exceeded(OrchestrationState(total_dispatches=4), limits) == "max_dispatches"
    assert guard_exceeded(OrchestrationState(messages_sent=6), limits) == "max_messages"
    assert guard_exceeded(OrchestrationState(total_cost_usd=10.5), limits) == "max_cost_usd"


def test_is_quiescent_only_when_idle_and_no_inflight():
    from domain.orchestration import is_quiescent

    assert is_quiescent(active_agents=0, in_flight_messages=0) is True
    assert is_quiescent(active_agents=1, in_flight_messages=0) is False
    assert is_quiescent(active_agents=0, in_flight_messages=2) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_orchestration.py -k "state or guard or quiescent" -v`
Expected: FAIL — `ImportError: cannot import name 'OrchestrationState'`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/domain/orchestration.py`:

```python
class OrchestrationLimits(BaseModel):
    """Anti-runaway bounds enforced by the workflow."""

    max_waves: int = 8
    max_dispatches: int = 20
    max_messages: int = 200
    max_cost_usd: float = 25.0


class OrchestrationState(BaseModel):
    """Immutable snapshot of a run's orchestration progress, fed to invoke_lead."""

    waves: int = 0
    total_dispatches: int = 0
    messages_sent: int = 0
    total_cost_usd: float = 0.0
    reports: list[AgentReport] = Field(default_factory=list)
    verdicts: list[MonitorVerdict] = Field(default_factory=list)

    def record_wave(self, *, dispatch_count: int, messages: int, cost: float) -> "OrchestrationState":
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


def guard_exceeded(state: OrchestrationState, limits: OrchestrationLimits) -> str | None:
    """Return the name of the first exceeded limit, or None. Used to force a BLOCK."""
    if state.waves > limits.max_waves:
        return "max_waves"
    if state.total_dispatches > limits.max_dispatches:
        return "max_dispatches"
    if state.messages_sent > limits.max_messages:
        return "max_messages"
    if state.total_cost_usd > limits.max_cost_usd:
        return "max_cost_usd"
    return None


def is_quiescent(active_agents: int, in_flight_messages: int) -> bool:
    """The system is quiescent when no agent is working and no message is in flight."""
    return active_agents == 0 and in_flight_messages == 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_orchestration.py -v`
Expected: PASS (12 tests).

- [ ] **Step 5: Commit**

```bash
git add src/domain/orchestration.py tests/unit/test_orchestration.py
git commit -m "feat: orchestration state, limits, guards, and quiescence policy"
```

---

## Task 4: Decision → Message / assignee mappings

**Files:**
- Modify: `src/domain/orchestration.py` (append)
- Test: `tests/unit/test_orchestration.py` (append)

These pure helpers turn a validated decision into persistable `Message` rows (Plan 1's model) and resolve the assignee. The caller supplies `role_to_agent_id` (built from the run's team).

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_orchestration.py`:

```python
def _role_map():
    return {AgentRole.LEAD: "a-lead", AgentRole.BACKEND: "a-eng", AgentRole.QA: "a-qa"}


def test_decision_to_messages_builds_dispatch_and_user_note():
    from domain.models import MessageKind, MessageRecipientKind, MessageSenderKind
    from domain.orchestration import decision_to_messages

    decision = OrchestrationDecision(
        intent=OrchestrationIntent.CONTINUE,
        dispatches=[Dispatch(target_role=AgentRole.BACKEND, instructions="build it")],
        messages=[OutboundMessage(recipient_kind=MessageRecipientKind.USER, body="starting")],
    )
    msgs = decision_to_messages(
        decision,
        owner_id="dev-user",
        lead_agent_id="a-lead",
        run_id="r1",
        work_item_id="w1",
        project_id="p1",
        role_to_agent_id=_role_map(),
    )
    assert len(msgs) == 2
    dispatch = next(m for m in msgs if m.kind == MessageKind.DISPATCH)
    assert dispatch.sender_kind == MessageSenderKind.AGENT and dispatch.sender_agent_id == "a-lead"
    assert dispatch.recipient_kind == MessageRecipientKind.AGENT
    assert dispatch.recipient_agent_id == "a-eng"
    assert dispatch.body == "build it" and dispatch.run_id == "r1"
    note = next(m for m in msgs if m.recipient_kind == MessageRecipientKind.USER)
    assert note.recipient_agent_id is None and note.body == "starting"


def test_decision_to_messages_skips_unknown_role():
    from domain.orchestration import decision_to_messages

    decision = OrchestrationDecision(
        intent=OrchestrationIntent.CONTINUE,
        dispatches=[Dispatch(target_role=AgentRole.DEVOPS, instructions="x")],
    )
    msgs = decision_to_messages(
        decision, owner_id="o", lead_agent_id="a-lead", run_id="r1",
        work_item_id=None, project_id=None, role_to_agent_id=_role_map(),
    )
    assert msgs == []  # DEVOPS not on the team -> nothing to deliver


def test_resolve_assignee_maps_role_to_agent():
    from domain.orchestration import resolve_assignee

    d = OrchestrationDecision(intent=OrchestrationIntent.VERIFY, assignee_role=AgentRole.BACKEND)
    assert resolve_assignee(d, _role_map()) == "a-eng"
    assert resolve_assignee(OrchestrationDecision(intent=OrchestrationIntent.VERIFY), _role_map()) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_orchestration.py -k "decision_to_messages or resolve_assignee" -v`
Expected: FAIL — `ImportError: cannot import name 'decision_to_messages'`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/domain/orchestration.py`:

```python
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
            recipient_agent_id = role_to_agent_id.get(m.recipient_role) if m.recipient_role else None
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_orchestration.py -v`
Expected: PASS (15 tests).

- [ ] **Step 5: Commit**

```bash
git add src/domain/orchestration.py tests/unit/test_orchestration.py
git commit -m "feat: map orchestration decisions to messages and assignee"
```

---

## Task 5: Lead-decision contract — prompt builder & parsing

**Files:**
- Create: `src/domain/orchestration_prompts.py`
- Test: `tests/unit/test_orchestration_prompts.py`

The contract = the prompt that tells the lead to emit a decision, plus the parser that validates the lead's raw dict into a typed `OrchestrationDecision` (raising a clear error so Plan 3 can do bounded retries). The transport (how Claude Code returns the dict) is Plan 3's concern.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_orchestration_prompts.py
import pytest

from domain.models import AgentRole
from domain.orchestration import OrchestrationIntent, OrchestrationState
from domain.orchestration_prompts import (
    OrchestrationContractError,
    build_orchestrator_prompt,
    parse_decision,
    parse_verdict,
)


def test_prompt_mentions_ticket_roles_and_state():
    prompt = build_orchestrator_prompt(
        task_title="Add login",
        acceptance_criteria=["users can log in"],
        body="OAuth",
        state=OrchestrationState(waves=1, total_cost_usd=2.0),
        available_roles=[AgentRole.BACKEND, AgentRole.QA],
    )
    assert "Add login" in prompt
    assert "users can log in" in prompt
    assert "backend" in prompt and "qa" in prompt          # available roles listed
    assert "continue" in prompt and "verify" in prompt      # intents described
    assert "wave" in prompt.lower()                          # state digest present


def test_parse_decision_validates_and_types():
    decision = parse_decision(
        {
            "intent": "continue",
            "dispatches": [{"target_role": "backend", "instructions": "do it"}],
            "assignee_role": "backend",
        }
    )
    assert decision.intent == OrchestrationIntent.CONTINUE
    assert decision.dispatches[0].target_role == AgentRole.BACKEND


def test_parse_decision_raises_contract_error_on_bad_payload():
    with pytest.raises(OrchestrationContractError):
        parse_decision({"intent": "continue"})  # continue with no dispatches/messages
    with pytest.raises(OrchestrationContractError):
        parse_decision({"intent": "nonsense"})  # not a valid intent


def test_parse_verdict_roundtrips():
    v = parse_verdict({"complete": False, "unmet": ["tests fail"]})
    assert v.complete is False and v.unmet == ["tests fail"]
    with pytest.raises(OrchestrationContractError):
        parse_verdict({"unmet": []})  # missing required 'complete'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_orchestration_prompts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'domain.orchestration_prompts'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/domain/orchestration_prompts.py
"""The lead-decision contract: orchestrator prompt + parsing of the lead's structured
output into typed decisions/verdicts. Pure (no runtime/transport concerns). No I/O."""

from pydantic import ValidationError

from domain.models import AgentRole
from domain.orchestration import MonitorVerdict, OrchestrationDecision, OrchestrationState


class OrchestrationContractError(ValueError):
    """The lead's output did not satisfy the decision/verdict schema."""


_INTENTS = (
    "continue (dispatch agents and keep going), "
    "verify (trigger the completion monitor), "
    "complete (only after a monitor pass), "
    "block (give up — requires a rationale), "
    "needs_human (open a human approval gate)"
)


def build_orchestrator_prompt(
    *,
    task_title: str,
    acceptance_criteria: list[str],
    body: str,
    state: OrchestrationState,
    available_roles: list[AgentRole],
) -> str:
    ac = "\n".join(f"- {c}" for c in acceptance_criteria) or "- (none given)"
    roles = ", ".join(r.value for r in available_roles) or "(none)"
    reports = "\n".join(
        f"- {r.role.value}: {r.outcome.value} — {r.summary}" for r in state.reports
    ) or "- (no reports yet)"
    return (
        "You are the team lead orchestrating a software task. Decide the next step; you do "
        "NOT do the work yourself. Respond ONLY with a JSON object matching the decision "
        "schema.\n\n"
        f"Ticket: {task_title}\n{body}\n\nAcceptance criteria:\n{ac}\n\n"
        f"Available agent roles you may dispatch: {roles}\n\n"
        f"Progress so far — wave {state.waves}, dispatches {state.total_dispatches}, "
        f"cost ${state.total_cost_usd:.2f}.\nReports:\n{reports}\n\n"
        f"Choose one intent: {_INTENTS}.\n"
        "Decision JSON fields: intent (required); dispatches (list of "
        "{target_role, instructions, acceptance[]}); messages (list of "
        "{recipient_kind: agent|user, recipient_role?, kind?, subject?, body}); "
        "assignee_role (the role primarily responsible); rationale (required for block). "
        "When all work appears done, use intent=verify to have the monitor confirm before "
        "you complete."
    )


def parse_decision(raw: dict) -> OrchestrationDecision:
    """Validate the lead's raw output into a typed decision, or raise a contract error."""
    try:
        return OrchestrationDecision.model_validate(raw)
    except ValidationError as exc:
        raise OrchestrationContractError(str(exc)) from exc


def parse_verdict(raw: dict) -> MonitorVerdict:
    """Validate the monitor's raw output into a typed verdict, or raise a contract error."""
    try:
        return MonitorVerdict.model_validate(raw)
    except ValidationError as exc:
        raise OrchestrationContractError(str(exc)) from exc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_orchestration_prompts.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/domain/orchestration_prompts.py tests/unit/test_orchestration_prompts.py
git commit -m "feat: lead-decision contract (orchestrator prompt + decision/verdict parsing)"
```

---

## Task 6: Gate check & PR

- [ ] **Step 1: Full suite + coverage**

Run: `make coverage`
Expected: PASS, ≥ 80% (the two new modules are pure and fully unit-tested).

- [ ] **Step 2: Lint**

Run: `make lint`
Expected: clean.

- [ ] **Step 3: Push and open PR**

```bash
git push -u origin <branch>
gh pr create --base main --title "feat: orchestration domain & guards (orchestration foundation, PR2)" \
  --body "Pure-domain types, guard/quiescence policy, decision->Message/assignee mappings, and the lead-decision contract (orchestrator prompt + parsing) for lead-driven orchestration (ADR-0002, Plan 2 of 3). No Temporal/persistence/HTTP. Consumed by Plan 3 (workflow & actors)."
```

---

## Self-Review

**Spec coverage (vs. `2026-06-14-lead-orchestration-design.md` §4–5):**
- `Dispatch`, `OrchestrationDecision` (+ intents + validation) → Task 1. ✓
- `AgentStepResult`, `MonitorVerdict` (+ `AgentReport`, `AgentOutcome`) → Task 2. ✓
- `OrchestrationState`, guard policy (`max_waves`/`max_dispatches`/`max_messages`/`max_cost_usd`), `is_quiescent` → Task 3. ✓
- decision→messages and decision→assignee mappings → Task 4. ✓
- Lead structured-output contract (prompt + parse, with a clear error for bounded retry) → Task 5. ✓
- *Deferred to Plan 3:* the Temporal transport for the contract, `RunWorkflow`/`AgentWorkflow`, activities, new `RunEventType`s, quiescence-timeout wiring.

**Placeholder scan:** none — every step has exact paths, real code, and concrete commands.

**Type consistency:** `OrchestrationIntent`/`Dispatch`/`OutboundMessage`/`OrchestrationDecision`/`AgentOutcome`/`AgentStepResult`/`AgentReport`/`MonitorVerdict`/`OrchestrationState`/`OrchestrationLimits` defined in Task 1–3 and reused with identical names/fields in Tasks 4–5; `decision_to_messages` builds `Message` using Plan 1's exact field names (`sender_kind`/`sender_agent_id`/`recipient_kind`/`recipient_agent_id`/`kind`/`body`/`run_id`/`work_item_id`/`project_id`/`owner_id`); `guard_exceeded` return strings match `OrchestrationLimits` field names.
