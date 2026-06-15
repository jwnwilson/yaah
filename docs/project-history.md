# yaah — Project History & Status

> **Read this first.** A consolidated, concise record of what has been built, what is
> dormant, and what is missing. Authored 2026-06-15 by consolidating every spec in
> `docs/specs/` and plan in `docs/plans/` against the merged git history. When this drifts
> from reality, fix it — it is the canonical orientation doc for a new session.

## What yaah is

A self-hosted platform for running **virtual dev teams** — role-based AI agents (lead,
architect, backend/frontend engineers, QA, devops) — against real repositories, driven from
a visual kanban board (projects → epics → features → tasks). Agents work in sandboxed Docker
containers with centrally managed secrets, permissions, skills, MCP servers, and models;
produce reviewable PRs; and update persistent memory as they work.

- Master design: [specs/2026-06-12-yaah-design.md](specs/2026-06-12-yaah-design.md)
- Architecture & patterns: [architecture.md](architecture.md)
- ADRs: [adr/](adr/) — **ADR-0002 (lead-driven orchestration) is the current architectural direction.**

**Build order:** Phase **A** (end-to-end spine) → Phase **C** (management plane) → Phase **B**
(full team). Prove the loop, make it observable/debuggable, then scale the team.

## Status at a glance

| Area | State |
|---|---|
| Phase A spine (A1–A6) | **Shipped** — real Claude Code runs produce real PRs |
| Phase C management plane | **Partial** — C1a + C2 UIs shipped; budgets/run-inspector/autonomy-dial pending |
| Lead-driven orchestration (ADR-0002) | **Live — the sole run path** (cutover done; `RunWorkflow` removed) |
| Deployment | **Spec only** — not yet validated locally or shipped remotely |
| Phase B (full team) | **Started** — orchestrator cutover landed as step 0; parallel engineers next |

## Phase A — the spine (shipped)

Each line is a merged increment; see the matching spec/plan for detail.

- **A1 control plane** — hexagonal foundation: repository + UnitOfWork, owner-scoping via
  required filters, `{success,data,error}` envelope, `CrudRouter`. **A1.5** refactored to the
  hexrepo `libs/db` + `libs/api` patterns (see architecture.md).
- **A2 board UI** — React/Vite/Tailwind SPA: 7-column kanban + Attention pool, project/epic/
  feature/task hierarchy, ticket slide-over, run lifecycle (start/cancel/approve/reject gate/
  edit). TanStack Query as the single source of server truth.
- **A3 Temporal pipeline** — durable run spine: `PLAN→PROVISION→IMPLEMENT→VERIFY→PR→LEARN`,
  gates as Temporal signals, VERIFY retry loop (max 3) then BLOCKED, crash-resume. Pure
  `domain/transitions/pipeline.py` decides; `FakeAgentRuntime` proved it with no LLM.
- **A4a workspaces + PRs** — real per-run workspace (local worktree / remote clone), real
  commit to `agent/<task-id>`, real GitHub PR via a GitHub App (per-run installation token).
- **A5a/b Claude runtime** — `ClaudeCodeRuntime` spawns `claude -p --output-format
  stream-json` per stage in a containerized worker; pure `stream_json.parse`; auto-falls back
  to `FakeAgentRuntime` without a key/binary.
- **A5c1 capability model** — `Skill`/`McpServer`/`Secret` tables + grants on
  `AgentDefinition` (`allowed_tools`, `skill_ids`, `mcp_server_ids`, `secret_ids`); deny-by-
  default; CrudRouter management endpoints; default team factory with per-role grants.
- **A5c2 runtime composition** — per-stage agent selection (role↔stage) assembles an
  `AgentManifest`; runtime composes the `claude` invocation (`--append-system-prompt`,
  allowed tools, cloned/mounted skills, generated `.mcp.json`).
- **A5c3a secret injection** — Fernet-encrypted, write-only secret values
  (`PUT /secrets/{id}/value`, reads expose `has_value` only); decrypted inside the activity
  and injected into the subprocess env + per-MCP `env`. Never enters Temporal history/logs.
- **A5c3b1 LiteLLM routing** — `LiteLLMProvider` (drop-in `ModelProvider`); per-agent
  `model_alias` becomes `--model`; `model_gateway` = `anthropic|litellm|auto`.
- **A5c3d1/d2 tool audit** — append-only `audit_events`; `capability_granted` per stage, plus
  an active **PreToolUse hook** enforcing the allowlist (deny-by-default) and ingesting
  `tool_allowed`/`tool_denied` decisions. Enforcement is outside the model.
- **A5d usage tracking** — append-only `usage_records` (per stage-execution per model,
  idempotent on resume); owner-scoped rollups task→feature→epic→project and by stage/role/
  model. Tracking only — **no enforcement.**
- **A5e notifications** — `Notification` inbox: system signals (gate opened, blocked/failed)
  + deliberate agent flags via a `yaah_notify` capability; pluggable channel port (in-app now).
- **A6a refinement chat** — synchronous lead-agent chat rail that proposes epics/features/
  tasks as `Draft` work items (never auto-promoted). `RefinementAgent` port (+ fake fallback).
- **A6b1/b2 project memory** — agents read `CLAUDE.md`/`AGENTS.md`/`docs/adr/` before plan/
  implement; LEARN curator's edits to those paths become durable, reviewable `MemoryProposal`
  artifacts on an `agent/memory-<run_id>` branch; human apply (local fast-forward / remote PR)
  or reject from the board; auto-apply under `full_auto`.

## Phase C — management plane (partial)

- **C1a** — global `AppLayout` header + `/manage` shell; Secrets / Skills / MCP-servers CRUD
  screens (write-only secret values); notification bell in the header.
- **C2** — Budget (usage rollup + group-by), Models (per-agent `model_alias` + grants editing),
  Audit log (paginated, filterable), Memory-proposals history (unified-diff viewer). Added
  `GET /usage`, `GET /audit`, `GET /memory-proposals`.
- **UI modern redesign** — dark-first design system: semantic CSS-variable tokens, in-repo
  primitives (`ui/src/ui/`), Inter font, all surfaces restyled. No new runtime UI deps.

## Lead-driven orchestration (ADR-0002) — the run path

The architectural pivot from a fixed pipeline to a **real orchestrator**: the lead decides
(structured `OrchestrationDecision` from an activity), and **Temporal executes each decision
durably** (orchestrator-worker pattern). Agents run as durable **`AgentWorkflow` child actors**
with signal-fed mailboxes that drain to idle; a parent **`OrchestratorWorkflow`** loops
`invoke_lead → dispatch → await quiescence → run_monitor` until the monitor confirms
acceptance. Live inter-agent messaging rides Temporal signals; a `Message` table is both the
durable mailbox and the UI inbox. Bounded by domain **guards** (max waves/dispatches/messages/
cost, quiescence timeout) so it can't run away.

**Everything is merged:** messaging substrate, domain + guards, activities (`invoke_lead`,
`agent_step`, `run_monitor`, `persist_messages`), `AgentWorkflow` actor, `OrchestratorWorkflow`
parent, monitor-bounded verify loop, assignee persistence, tool-audit parity. The
**agent-visibility UI** (team roster, agent detail + output, inbox/mailbox switcher, assignee
chip with active-now ring) is also merged.

**Cutover done (Phase B step 0).** The orchestrator is now the **sole run path**: every run
starts `OrchestratorWorkflow`, the `orchestrator_enabled` flag and the legacy fixed-stage
`RunWorkflow` are removed. Before flipping, the simplified path was hardened to the old
pipeline's fidelity — actors now return their real worst outcome + cost (the parent records a
truthful report and threads cost into the run + cost guard, replacing the hardcoded `OK`/`0.0`),
and the peer-routing id is fixed. Current shape is **one actor per role per wave** (gathered to
completion before the next); true concurrency/quiescence/live-messaging is the parallel-engineers
spec. One follow-up left from the cutover: remove the now-orphaned `run_stage` activity +
`pipeline.STAGES`/`should_retry_verify` once their secret-injection/audit tests are migrated onto
`agent_step`.

## Architecture snapshot (current)

- **16 tables:** projects, work_items, teams, skills, mcp_servers, secrets, agent_definitions,
  runs, run_events, notifications, messages, audit_events, chat_sessions, chat_messages,
  usage_records, memory_proposals. **Alembic migrations** in `migrations/versions/` (replaced
  the A1 `create_all`).
- **Domain (pure):** `models`, `errors`, `memory`, `notifications`, `permissions`, `refinement`,
  `scm`, `teams`, `usage`; packages `transitions/` (pipeline + run + work-item machines),
  `orchestration/` (core + prompts), `agent/` (capabilities, invocation, prompts, runtime).
- **Adapters:** `database/` (repo + UoW + ports), `storage/` (local; S3 planned), `git/`
  (local_git + github_app + fake), `skills/` (fetcher), `agent/` (`runtime/` claude_code +
  fake + pretooluse_hook + stream_json; `model/` anthropic + litellm + fake; `refinement/`;
  `notify/`).
- **Interactors:** `api/` (app, auth, deps, envelope, settings, routes), `temporal/`
  (workflows, activities, worker, client, config), `cli/` (seed, memory_apply).
- **Workflows:** `OrchestratorWorkflow` (parent) + `AgentWorkflow` (child actor) — the sole
  run path. (`run_stage` activity + `pipeline.STAGES`/`should_retry_verify` linger as orphaned
  dead code pending a test-migration follow-up.)
- **lib/:** `crud_router`, `secrets` (Fernet cipher).

## Gaps & open threads

Ordered roughly by leverage.

1. **Orchestrator cutover follow-ups** — the cutover landed (orchestrator is the sole path),
   but (a) it has not yet been exercised against a **real Claude run** end-to-end (fake e2e is
   green), and (b) the orphaned `run_stage` activity + `pipeline.STAGES`/`should_retry_verify`
   still need removing once their secret/audit tests move onto `agent_step`. Next Phase B
   increment that builds on it: **parallel same-role engineers** (real concurrent waves +
   quiescence + live messaging).
2. **Deployment unproven** — TODO.md's top three: validate locally, ship CI/CD, validate
   remotely. The deployment spec (K8s/Terraform/GitHub Actions) is written but nothing is
   shipped. Auth0 wiring deferred; single dev-user only.
3. **Budget enforcement** — usage is tracked but never gates a run; no caps, no pause-on-
   breach. A5e has the alert seam but it's inert until a threshold is configurable (Phase C).
4. **Project-management UX is thin** (TODO.md) — no epic detail view, no epic→feature
   breakdown flow, no ticket attachments/artifacts (`.md`, images).
5. **Phase C remainder** — run inspector (transcripts/costs), autonomy-dial UI, model
   registry / validated alias picker, LiteLLM gateway config UI, budget limits UI.
6. **Phase B (full team)** — parallel same-role engineers, role memory (A6b-3, deferred),
   pgvector RAG capability, a second runtime adapter (OpenHands/CrewAI), multi-user RBAC.
7. **Smaller deferrals** — memory-branch GC, conflict-resolution UI, message threading/replies,
   realtime sockets (polling only today), secret rotation/versioning, response/log redaction
   of agent-echoed secrets (the descoped C3c egress-broker work).

## Decisions worth remembering

- **ADR-0001** — `make db-reset` clears **both** Postgres and the Temporal `temporaldata`
  volume, then re-seeds via `cli/seed.py`, because orphaned workflows retry against missing rows.
- **ADR-0002** — lead-driven orchestration (above). Supersedes the design spec's "workflow is
  the sole supervisor" and "lead cannot trigger agents" statements.
- **C3c egress proxy / credential broker is descoped** for single-user local: per-agent grants
  + per-stage scoped secret injection are sufficient; open egress is acceptable. Returns only
  for multi-tenant / remote hardening.
