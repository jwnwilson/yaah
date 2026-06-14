# ADR-0002: Lead-driven orchestration with durable actor mailboxes

**Date**: 2026-06-14
**Status**: accepted
**Deciders**: noel

## Context

yaah's goal is an agent harness where the **team lead is an orchestrator agent that triggers other agents** — not a fixed pipeline. The original design (`docs/specs/2026-06-12-yaah-design.md`) deliberately chose the opposite: "the workflow is the supervisor — the lead is invoked per-stage and exits" (§ Supervision & liveness), and rejected agent-as-orchestrator (CrewAI) citing the MAST study that role-played orchestration is where multi-agent dev teams fail. The current code reflects the original choice: `RunWorkflow` iterates a hardcoded stage list (`PLAN→PROVISION→IMPLEMENT→VERIFY→PR→LEARN`) and `capabilities.select_agent` picks one agent per stage; the lead is merely the agent for PLAN/LEARN and cannot trigger anyone.

We are reversing the agent-as-orchestrator rejection **while keeping Temporal's durability**, by separating *deciding* from *executing*. This ADR records the architecture so future sessions don't re-derive the now-superseded "workflow is the sole supervisor" model.

## Decision

Adopt an **orchestrator-worker** architecture (Anthropic's pattern, already cited in the design spec) with concurrent durable actors:

1. **Lead decides, Temporal executes.** An `invoke_lead` activity runs the lead agent with the ticket + memory + current orchestration state and returns a **structured `OrchestrationDecision`** (intent + `Dispatch[]` + messages + `assignee_role`). The lead never executes work itself; the workflow runs each dispatch.
2. **Agents are durable child-workflow actors.** Each dispatched agent is a Temporal child workflow (`AgentWorkflow`) with a signal-fed `inbox`. The lead's `RunWorkflow` is the parent.
3. **Agents talk live, mid-run.** An agent messages a peer by signalling the peer's `AgentWorkflow` (`deliver`). Temporal provides durable, ordered, exactly-once delivery — no external broker. Every delivered signal is also written to the `messages` table for the UI/forensics.
4. **Drain-until-empty mailboxes.** Each agent loops: wait for inbox-non-empty-or-work-pending, then fully drain the inbox (one `agent_step` Claude Code activity per message, which may emit outgoing messages), and mark itself done only when idle **and** inbox is empty.
5. **Lead proposes completion, monitor confirms.** At global quiescence (all agents idle, no messages in flight) the lead triggers a **MONITOR** step (`run_monitor`) that independently verifies acceptance criteria are met and mailboxes are empty, returning a `MonitorVerdict`. The lead re-dispatches if incomplete; only a monitor pass allows `complete`.
6. **Messaging substrate is a first-class `Message` entity** (separate from `Notification`; see ADR-0001's spirit of not overloading existing types). It is both the agent mailbox and the user-facing inbox row.
7. **Tickets gain `assignee_agent_id`**, set by the lead's `assignee_role` decision and user-overridable.
8. **Bounded authority / anti-runaway guards.** The lead can only dispatch known roles, set parallelism, or emit a terminal verdict — no arbitrary control flow. The workflow enforces `max_waves`, `max_dispatches`, `max_messages_per_run`, `max_cost_usd`, and a quiescence timeout; long-lived agent workflows use `continue-as-new`. Human approval gates still interrupt anywhere.

**Build order:** the orchestration foundation (this ADR's mechanics + `Message` + `assignee`) is specced and built first; the agent-visibility UI (team roster, per-agent output, inbox, assignee chip) is a second spec that visualizes this foundation.

## Alternatives Considered

### Alternative 1: Keep "workflow is the sole supervisor" (status quo)
- **Pros**: Simplest; fully durable; already built.
- **Cons**: The lead cannot trigger agents — it is not an orchestrator. Fails the project's stated goal.
- **Why not**: Direct conflict with the harness goal of a lead that drives the team.

### Alternative 2: Long-running lead process with native sub-agents (CrewAI-style)
- **Pros**: Simplest "agent triggers agent"; uses Claude Code's own sub-agent tools.
- **Cons**: A crash kills the whole tree mid-run; no per-agent sandbox/capability isolation; this is the exact MAST/CrewAI failure mode the original spec rejected.
- **Why not**: Discards the durability that motivated choosing Temporal.

### Alternative 3: Lead plans a static task-DAG once; workflow executes it (no live re-planning)
- **Pros**: Durable, cheaper on tokens, no concurrent chatter.
- **Cons**: No live mid-run agent-to-agent messaging; lead can't react except at checkpoints.
- **Why not**: The requirement explicitly includes agents talking while they run and draining mailboxes — a static DAG can't express that. (It remains a valid *simpler-v1 shape* to grow from.)

### Alternative 4: Activities polling a DB queue, or an external broker (Redis/NATS)
- **Pros**: DB-polling is a simple mental model; a broker scales to heavy concurrency.
- **Cons**: Polling means delivery-latency = poll interval and weaker ordering; a broker adds infra the single-user-local design avoids.
- **Why not**: Temporal child-workflow signals already give durable, ordered, exactly-once delivery for free.

## Consequences

### Positive
- The lead is a real orchestrator: it triggers agents, assigns the ticket, and gates completion via an independent monitor.
- Concurrency and live inter-agent messaging without new infrastructure — Temporal signals are the bus.
- Crash-safety preserved: lead decisions and agent turns are persisted activity results; runs resume mid-flight.
- The `Message` model simultaneously powers orchestration and the planned inbox UI.

### Negative
- The fixed-stage `RunWorkflow` is replaced by a dynamic parent/child-actor workflow — materially more complex than the current loop.
- Concurrent multi-agent chatter is the ~15× token cost the design spec warns about; guards are mandatory, not optional.
- Two writes per message (Temporal signal + `messages` row) for observability.

### Risks
- **Runaway loops / cost blowup** — mitigated by the bounded-authority schema and workflow guards (max waves/dispatches/messages/cost, quiescence timeout).
- **Workflow history growth** in long-lived agent actors — mitigated with `continue-as-new`.
- **Non-termination / false-complete** — mitigated by quiescence detection plus the independent monitor verifying acceptance before `complete`.

## Supersedes / amends

Amends `docs/specs/2026-06-12-yaah-design.md`: the "Orchestration spine" row's rejection of agent-as-orchestrator and the "workflow is the supervisor" statement (§ Supervision & liveness) are superseded by this ADR. Temporal remains the durable execution spine; what changes is that the lead now decides the DAG within bounded rails.
