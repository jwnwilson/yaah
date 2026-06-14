# Lead-driven orchestration — design spec

**Date**: 2026-06-14
**Status**: approved (brainstorm) — implementation plan to follow
**Decision record**: [ADR-0002](../adr/0002-lead-driven-orchestration.md)
**Supersedes**: the "workflow is the sole supervisor" model in [2026-06-12-yaah-design.md](2026-06-12-yaah-design.md)

## 1. Goal

Make the **team lead a real orchestrator agent**: it triggers other agents, assigns the
ticket, and gates completion — instead of the current fixed `PLAN→IMPLEMENT→VERIFY→PR→LEARN`
pipeline where the lead is just the PLAN/LEARN agent. Agents run **concurrently as durable
Temporal actors**, talk to each other **live mid-run**, and **drain their own mailbox until
empty**. Temporal stays the durable executor, so crash-resume and human gates are preserved.

This is the **foundation** spec. A second spec covers the agent-visibility UI (team roster,
per-agent output, message inbox, ticket assignee chip) as an observability layer on top.

## 2. Principle: separate *deciding* from *executing*

The lead **decides**; Temporal **executes**. The lead is invoked as an activity that returns a
structured decision — it never runs work itself. The workflow executes each decision durably.
This is the orchestrator-worker pattern (already cited in the design spec) and is what lets the
lead drive the team without discarding durability or falling into the MAST/CrewAI failure mode
(role-played orchestration with no durability). The lead's authority is **bounded by a schema**:
it may dispatch known roles, message agents, trigger the monitor, or emit a terminal verdict —
no arbitrary control flow.

## 3. Architecture

```
┌────────────────── RunWorkflow (parent — the lead's run) ───────────────────┐
│ PROVISION ─▶ lead dispatches agents ─▶ …quiescence… ─▶ MONITOR ─▶ PR ─▶ LEARN│
│                       │                                   ▲                  │
│         spawns persistent child-workflow actors    lead triggers + verifies  │
│                       ▼                                                       │
│  ┌ AgentWorkflow: engineer ┐  ┌ AgentWorkflow: qa ┐  ┌ AgentWorkflow: … ┐    │
│  │ inbox (signal-fed)       │◀▶│ inbox             │◀▶│  live peer signals│    │
│  │ drain until empty:       │  │ drain until empty │  │                   │    │
│  │   agent_step (Claude)    │  │   agent_step      │  │                   │    │
│  │   emit msgs → peers      │  │   emit msgs       │  │                   │    │
│  │ idle when work+inbox==∅  │  │ idle when ∅       │  │                   │    │
│  └──────────────────────────┘  └───────────────────┘  └───────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────┘
```

- **Agents are persistent actors for the life of a run** (not re-spawned per wave). The parent
  owns lifecycle + quiescence detection; the lead is the brain invoked at each quiescence point;
  agents are child workflows that work, message peers, and drain their inbox.
- **Inter-agent messaging = Temporal signals.** An agent messages a peer by signalling the
  peer's `AgentWorkflow` (`deliver`). Temporal gives durable, ordered, exactly-once delivery —
  no external broker. Messages to the **user** go to the durable user mailbox (no workflow).
- **Every delivered signal is also written to the `messages` table** for the UI inbox and
  crash-forensics.

## 4. Domain model & contracts (pure, no I/O)

### `Message` — durable mailbox unit *and* UI inbox row (separate from `Notification`)

| Field | Type | Purpose |
|---|---|---|
| `id, owner_id, created_at` | — | owner-scoped |
| `sender_kind` | `agent \| system \| user` | lead is `agent`, role=LEAD |
| `sender_agent_id` | `str \| None` | required when `sender_kind==agent` |
| `recipient_kind` | `agent \| user` | which mailbox |
| `recipient_agent_id` | `str \| None` | required when `recipient_kind==agent` |
| `kind` | `dispatch \| report \| chat \| status` | orchestration semantics |
| `subject, body` | `str` | content |
| `run_id, work_item_id, project_id` | `str \| None` | context links (agent mailboxes are per-run) |
| `delivered_at` | `datetime \| None` | signal delivered to the actor |
| `processed_at` | `datetime \| None` | agent drained/handled it ("until empty") |
| `read_at` | `datetime \| None` | user-facing read state (UI only) |

Validator: agent kinds require the matching `*_agent_id`.

### `Dispatch` — the lead's "trigger an agent" unit
`target_role: AgentRole`, `instructions: str` (brief the lead writes), `acceptance: list[str]`.
Parallelism = multiple dispatches in one decision.

### `OrchestrationDecision` — the lead's validated structured output
- `intent: continue | verify | complete | block | needs_human`
- `dispatches: list[Dispatch]`
- `messages: list[OutboundMessage]` (lead notes beyond dispatch)
- `assignee_role: AgentRole | None` (→ sets `WorkItem.assignee_agent_id`)
- `rationale: str`
- Validation: `continue` requires dispatches or messages; `block` requires a reason;
  `complete` only honored after a monitor pass.

### `MonitorVerdict`
`complete: bool`, `unmet: list[str]` (failed acceptance), `pending_mailboxes: list[str]`
(actors not idle/drained), `notes: str`.

### `WorkItem.assignee_agent_id: str | None`
Set from the lead's `assignee_role`; user-overridable via `PATCH /work-items/{id}`.

### New `RunEventType`s
`AGENT_DISPATCHED`, `AGENT_REPORTED`, `MONITOR_STARTED`, `MONITOR_VERDICT`, `QUIESCENCE_REACHED`.

### Guard policy (`domain/orchestration.py`, pure)
`max_waves`, `max_dispatches`, `max_messages_per_run`, `max_cost_usd`, `quiescence_timeout`;
`is_quiescent(active_agents, in_flight_messages)`; guard-exceeded detection → forces `block`.

## 5. Workflow & actor mechanics

**Parent `RunWorkflow`** (replaces the fixed `STAGES` loop):
```
run(inp):
  await provision_workspace(...)                  # mechanical, unchanged
  state = OrchestrationState()
  while True:
      decision = await invoke_lead(state)         # activity → OrchestrationDecision
      persist(events, assignee, lead→* messages)
      match decision.intent:
        block       → return BLOCKED(reason)
        needs_human → await gate()                 # wait_condition(approve/reject/cancel)
        verify      → v = await run_monitor(state) # lead TRIGGERS the monitor
                      if v.complete: break
                      else: state.add(v); continue
        continue    → if guards_exceeded(state): return BLOCKED("guard")
                      for d in decision.dispatches:
                          h = state.actor(d.target_role) or start_child(AgentWorkflow, d)
                          h.signal deliver(dispatch_message(d))
                      await quiescence(state)
                      state.collect_reports()
  for h in state.actors: h.signal stop_now()
  await open_pr(...); await capture_memory(...); return DONE
```

**Child `AgentWorkflow`** (the actor — drain-until-empty):
```
inbox=[]; idle=False; stop=False
@signal deliver(msg): inbox.append(msg); idle=False
@signal stop_now():   stop=True
@query  queue_depth(): return len(inbox)
@query  is_idle():     return idle
run(ctx):
  while not stop:
      await wait_condition(inbox OR stop)
      while inbox and not stop:                    # DRAIN until empty
          msg = inbox.pop(0)
          r = await agent_step(ctx, incoming=msg)  # one Claude Code turn (activity)
          persist(msg.processed_at, events, usage)
          for out in r.outgoing:                   # talk to peers, live
              persist(out); signal_peer(out)
          if r.completed_brief: signal_lead(report(...))
      idle = True
      if history_too_long(): continue_as_new(inbox, idle)
```

**Activities** (generalizing today's code):
- `invoke_lead(state) → OrchestrationDecision` — orchestrator prompt (lead persona + ticket +
  acceptance + digest of live agents/reports/messages/costs/prior verdicts); validates the
  decision (constrained decision tool or final-JSON contract; bounded retry on schema miss).
- `agent_step(run, role, incoming, workspace) → AgentStepResult{outgoing, completed_brief,
  artifacts, cost_usd, outcome}` — generalizes today's `run_stage`; the incoming message/brief
  is the task input (replacing static `prompts.for_stage`); runs Claude Code in the sandbox.
- `run_monitor(state) → MonitorVerdict` — independent completion check (all actors idle/
  terminated, mailboxes empty, acceptance verified by a checker or the QA agent).

**Quiescence detection:** after a dispatch wave the parent loops `wait_condition` until every
actor's `is_idle()` query is true *and* a short settle-timer window passes with no new
`deliver`. `quiescence_timeout` guard blocks if it never settles.

**Human gates & cancel:** unchanged mechanism (`wait_condition` on `approve`/`reject`/`cancel`),
fired by autonomy policy (e.g. always gate before PR) or lead `needs_human`; cancel `stop_now`s
all actors.

## 6. Data flow, persistence & error handling

Persistence (all owner-scoped via UoW):
- **`messages`** — one row per delivered signal (`delivered_at` on send, `processed_at` on drain).
- **`run_events`** — extended event types feed the run timeline / per-agent output.
- **`usage_records`** — `agent_step`/`invoke_lead`/`run_monitor` record usage (carries `agent_role`)
  so per-agent + per-run cost rolls up and guards read live cost.
- **`work_items.assignee_agent_id`** — written by the lead, user-overridable.

Error handling:
- **Invalid lead decision** → bounded retry with the validation error appended → else `BLOCKED`.
- **Worker `agent_step` failure** → `outcome=fail` report to the lead (durable re-plan); transient
  infra failures use Temporal activity retry first.
- **Capability denial** → dispatch rejected, surfaced as a report to the lead (never silent).
- **Guard exceeded** → `BLOCKED` naming the specific guard (no silent truncation).
- **Crash mid-run** → Temporal resumes from the last completed activity; actor `inbox`/`idle`
  survive via workflow state + `continue-as-new`; `messages` reconstructs mailbox history.
- **Stuck/non-terminating** → quiescence timeout + monitor `unmet`/`pending_mailboxes` make
  failure legible instead of a hang.

## 7. Testing (TDD, 80% gate)

- **Domain (pure):** decision/dispatch/verdict/message validation; guard + quiescence policy;
  decision→messages and decision→assignee mapping; orchestrator-prompt builder.
- **Workflow (Temporal test env):** scripted fake `invoke_lead`/`agent_step`/`run_monitor`
  asserting single-wave, parallel dispatch, peer message delivered+drained, worker-fail→re-dispatch,
  guard→block, quiescence detection, monitor incomplete→re-loop→complete, gate interleave, cancel
  stops actors.
- **Integration:** `FakeAgentRuntime` lead emitting a canned multi-wave plan drives a real run
  end-to-end (extends `make e2e-fake`); assert messages, assignee, events, completion.
- Keep existing gate/cancel/cost tests green.

## 8. Scope boundaries (YAGNI for v1)

- Dispatch **by role** to the team's single agent of that role; multiple same-role workers
  (parallel engineers) is a Phase-B extension.
- **Reuse Claude Code** runtime — no new adapter.
- `Message` model + `assignee` field land **here** (substrate); the inbox UI, team roster,
  per-agent output view, and assignee chip are **Spec 2**.
- No external broker, no RAG, no message threading/replies (flat + context links).
- Monitor is **lead-triggered on demand**, not a standing watchdog.

## 9. Open implementation questions (for the plan, not blocking design)

- Exact lead structured-output mechanism on Claude Code (constrained decision tool via MCP vs.
  parse-final-JSON-block) — pick during planning; the contract is the `OrchestrationDecision` schema.
- `continue-as-new` history threshold value.
- Whether `run_monitor` reuses the QA agent or a dedicated lightweight checker for acceptance.
