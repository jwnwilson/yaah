# yaah A5e — Notification System (Design)

**Date:** 2026-06-13
**Status:** Approved design, pending implementation plan
**Phase:** A5e (management-plane capability surfaced early; also a phase-C / A6 building block)
**Depends on:** A2 (board UI), A3 (Temporal pipeline + `run_events` + gates), A5ab (Claude Code runtime + `stream_json`), A5c (agent capability grants). A5d (usage tracking) is an **optional** producer (budget-threshold alert) and is cross-referenced, not required.

## 1. Problem & goal

A run already emits structural signals — a gate opens (`awaiting_approval`), a run gets
`blocked` or `failed` — but they live only in the per-run `run_events` feed the board polls.
There is no way for the **lead developer agent** to deliberately flag something to the user
("I chose Postgres over SQLite, here's why", "PR ready for your review", "still working,
verify is flaky"), and no single place the user looks to see everything needing their
attention across all projects.

A5e adds a first-class **`Notification`** entity and an owner-scoped **inbox**: a durable,
filterable list of items raised either by the **lead agent** (in-band, via a granted
capability) or by the **pipeline** (gate opened / run blocked / run failed, plus a future
budget-threshold alert). Delivery is in-app now, behind a pluggable **channel port** so
email/Slack/push can be added later without reworking the core. Agent-raised items are
**non-blocking** flags; a free-form "agent pauses to ask a question" dynamic gate is
explicitly deferred.

### A5e success criterion

> When a `gated_all` run reaches its plan gate, an **action-required** notification appears in
> the inbox deep-linking to approve/reject; approving the gate auto-resolves it. Separately,
> the lead agent calls its `yaah_notify` capability during IMPLEMENT and a **decision**
> notification appears in the same inbox with the agent's title/body — the run keeps going.
> A `failed` run produces a **critical alert**. The unread badge reflects all three; marking
> read/resolved updates it. Everything is owner-scoped.

## 2. Scope

### In scope
- A **`Notification`** domain DTO (categories decision/review/update/alert; severity;
  source agent/system; nullable context links; nullable `action`).
- Pure **`notification_for_event(run_event) -> Notification | None`** policy (system producer).
- A new **`notification`** `AgentEvent` type + parser support so the lead agent can raise
  notifications **in-band** through the runtime (the `yaah_notify` capability — Approach 1).
- A **`NotificationDispatcher`** + **`NotificationChannel`** port (`adapters/notify/ports.py`);
  in-app persistence wired now; external channels are future adapters.
- **Auto-resolve**: a `gate_resolved` event resolves the linked action-required notification.
- Persistence (`Notification` table, repo, UoW, Protocol) and an owner-scoped **inbox API**:
  list (filterable), unread-count, mark-read, resolve.
- A board-UI **inbox** (bell + unread badge, grouped list, deep-links).

### Out of scope (later phases)
- **Blocking / dynamic gates** raised by the agent (run pauses until the user answers a
  free-form question) — needs new Temporal signal plumbing + a response contract; its own spec.
- **External channels** (email/Slack/push) — only the port + in-app channel ship; no SMTP,
  no provider secrets, no delivery-retry/queue.
- **Budget-threshold alert** — the producer hook is defined but **inert until A5d** lands a
  spend read + a configured threshold (phase C); A5e ships the mapping seam only.
- **Per-channel user preferences / digests / quiet hours** — deferred with the channels.
- **Notification editing or public create endpoint** — creation is internal only (§6/§9).

## 3. Decisions log

| Decision | Choice | Rationale |
|---|---|---|
| Agent raise mechanism | **In-band `yaah_notify` capability → `notification` `AgentEvent` → persisted by the activity** (Approach 1) | Reuses the existing event→activity→DB path; no DB creds or network egress from the sandbox; fits the A5c capability/MCP model |
| Rejected: direct REST call | **No** | Punches an egress hole from the sandbox to the control plane + token mgmt; fights the A4 egress-proxy posture |
| Rejected: stdout sentinel | **No** | Brittle, schema-less, tightly parser-coupled |
| Producers | **Both** — pure system policy + agent capability | The user's ask ("agent flags decisions/reviews/updates") plus structural events (gate/blocked/failed) belong in one inbox |
| Categories | **decision / review / update / alert** | The user's three agent-facing categories + `alert` for system structural/critical events |
| Agent decisions | **Non-blocking flags** | Existing gates already block; arbitrary agent-initiated blocking is a bigger, separate feature |
| Gate surfacing | **`gate_opened` → action-required `review`; `gate_resolved` → auto-resolve** | The inbox links to the *existing* approve/reject; no second approval mechanism, no orphaned items |
| Delivery | **Dispatcher + `NotificationChannel` port; in-app only now** | Pluggable later (email/Slack/push) with zero core rework |
| Creation surface | **Internal only (activities)** — no public `POST /notifications` | Keeps creation trusted + owner-scoped; clients only read/read-mark/resolve |

## 4. Architecture

```
src/
  domain/
    models.py            # + Notification DTO + NotificationCategory/Severity/Source enums + NotificationAction
    notifications.py     # PURE: notification_for_event(run_event) -> Notification | None; auto-resolve match
    runtime.py           # AgentEvent.type gains "notification"; data carries the agent's payload
  adapters/
    runtime/
      stream_json.py     # recognise the yaah_notify tool-call -> AgentEvent(type="notification", data=...)
      fake.py            # FakeAgentRuntime can script notification events
    notify/
      ports.py           # NotificationChannel Protocol (deliver) + NotificationDispatcher
      inapp.py           # in-app channel (persistence is the delivery); fake channel for tests
    database/
      orm.py             # + NotificationRow
      repositories.py    # + NotificationRepository
      uow.py             # + uow.notifications
      ports.py           # + notifications on UnitOfWork Protocol; + Notification in Repository set
  interactors/
    temporal/
      activities.py      # record_event also runs notification_for_event -> dispatcher;
                         # run_stage persists "notification" AgentEvents; gate_resolved auto-resolves
    api/
      routes/notifications.py  # GET / (list+filter), GET /unread-count, PATCH /{id} (read/resolve)
ui/                      # board header bell + unread badge + inbox panel (deep-links)
tests/
  unit/                  # notification_for_event mapping; auto-resolve match; parser tool-call -> event
  integration/           # inbox endpoints; gate_opened -> action-required; approve -> auto-resolve; dispatcher+fake channel
```

## 5. Domain — `Notification`

`domain/models.py`:

```python
class NotificationCategory(StrEnum):
    DECISION = "decision"   # agent flags a choice it made / recommends
    REVIEW   = "review"     # something to review (plan/PR ready) — usually action-required
    UPDATE   = "update"     # informational progress
    ALERT    = "alert"      # system: blocked / failed / (future) budget threshold

class NotificationSeverity(StrEnum):
    INFO = "info"; ATTENTION = "attention"; CRITICAL = "critical"

class NotificationSource(StrEnum):
    AGENT = "agent"; SYSTEM = "system"

class NotificationAction(BaseModel):
    kind: Literal["gate_approval"]      # the only action kind in A5e
    run_id: str

class Notification(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    source: NotificationSource
    category: NotificationCategory
    severity: NotificationSeverity = NotificationSeverity.INFO
    title: str
    body: str = ""                      # markdown
    run_id: str | None = None
    work_item_id: str | None = None
    project_id: str | None = None
    action: NotificationAction | None = None
    read_at: datetime | None = None
    resolved_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
```

Lifecycle: created (unread) → `read_at` set → `resolved_at` set. All transitions are
immutable `model_copy(update=…)`. Derived status for the API: `unread` (no `read_at`),
`read` (`read_at`, no `resolved_at`), `resolved` (`resolved_at`).

`domain/notifications.py` (pure):

```python
def notification_for_event(ev: RunEvent, *, run) -> Notification | None:
    # gate_opened -> REVIEW, ATTENTION, action=gate_approval(run_id)
    # blocked     -> ALERT, ATTENTION
    # error       -> ALERT, CRITICAL
    # else        -> None
    ...

def resolves(notification: Notification, ev: RunEvent) -> bool:
    # True when ev.type == gate_resolved and notification.action.run_id == ev.run_id
    ...
```

## 6. Producers

**System (pipeline).** The `record_event` activity, after appending the `run_event`, runs
`notification_for_event(ev, run=...)`; a non-`None` result is handed to the
`NotificationDispatcher`. On a `gate_resolved` event it instead loads the run's open
action-required notification(s) and, where `resolves(...)` is true, marks them resolved.
Mapping and matching are **pure**; the activity only wires I/O.

**Agent (in-band).** The lead agent's `AgentDefinition` is granted a `yaah_notify` capability
(allowed-tool / MCP entry — concrete transport settled in the plan). When the agent invokes
it, the call surfaces in the runtime's `stream-json`; `stream_json.parse` recognises that
tool-call and emits `AgentEvent(type="notification", data={category, title, body, severity})`.
`run_stage` persists such events (source=`AGENT`, with the current `run_id`/`work_item_id`/
`project_id` context) through the dispatcher, in addition to the normal `run_event` trail.
`FakeAgentRuntime` scripts `notification` events so the path is testable without a real model.

## 7. Delivery — dispatcher + channel port

`adapters/notify/ports.py`:

```python
class NotificationChannel(Protocol):
    def deliver(self, n: Notification) -> None: ...

class NotificationDispatcher:
    def __init__(self, uow_factory, channels: list[NotificationChannel]): ...
    def dispatch(self, n: Notification) -> None:
        # 1) persist (always)  2) fan out to each channel  (in-app = persistence, so a no-op deliver)
        ...
```

A5e wires only the in-app path (persist → inbox API → board UI). `EmailChannel`,
`SlackChannel`, `PushChannel` are future adapters implementing `NotificationChannel`; adding
one needs no change to producers or the dispatcher contract. A channel failure is logged and
never blocks persistence (the inbox is the source of truth).

## 8. Persistence

- `NotificationRow` in `orm.py`; `NotificationRepository`; `uow.notifications`; Protocol
  additions. Rows **are** updated (read/resolve timestamps) — unlike `run_events`/`usage`.
- Owner-scoped; activities supply the run's `owner_id` as the required filter.
- `create_all` picks up the new table (alembic deferred per A1.5).

## 9. Inbox API (owner-scoped, enveloped)

- `GET /notifications?category=&status=unread|read|resolved&page_size=&page_number=&order_by=`
  — paginated list (`status` derived from the timestamps; default `-created_at`).
- `GET /notifications/unread-count` → `{count}` for the header badge.
- `PATCH /notifications/{id}` with `{read: true}` and/or `{resolved: true}` — sets the
  corresponding timestamp(s) via immutable update; idempotent.
- **No public create** — notifications originate only from activities (§6). Acting on an
  action-required item (`action.kind == "gate_approval"`) is done through the **existing**
  `POST /runs/{id}/approve|reject`; the resulting `gate_resolved` auto-resolves the
  notification (§6). The UI deep-links there.

## 10. Board UI

A bell in the board header with an unread badge (`/unread-count`); a panel lists notifications
grouped by category, newest first, each with severity styling and a deep-link (run drawer /
work-item / approve-reject for action-required). Mark-read on open; explicit resolve/dismiss.
Follows existing A2 board patterns and the `{success,data,error}` envelope.

## 11. Error handling

- `notification_for_event` is total: unmapped event types return `None` (no notification),
  never raise.
- Dispatcher persists first; a channel `deliver` exception is logged and swallowed so it can't
  lose the inbox item or fail the run.
- Malformed `yaah_notify` payloads (missing title / bad category) are dropped with a logged
  warning and a normal `run_event` noting the rejection — they never crash the stage.
- `PATCH` validates the body; resolving an already-resolved item is a no-op 200.

## 12. Testing (80% gate)

- **Domain (pure):** `notification_for_event` for gate_opened/blocked/error/other; `resolves`
  matching; immutability of read/resolve updates.
- **Parser:** a `yaah_notify` tool-call line → `notification` `AgentEvent`; malformed payload
  dropped.
- **Repo:** create/update/owner-scoping for `Notification`.
- **Dispatcher:** persists + invokes a fake channel; a throwing channel doesn't prevent
  persistence.
- **API (integration):** list + filters + unread-count + mark-read/resolve; `gate_opened`
  produces an action-required notification and `POST /runs/{id}/approve` auto-resolves it; a
  scripted agent `notification` event lands in the inbox as source=`AGENT`; owner scoping.

## 13. Risks

- **In-band transport coupling** — recognising the `yaah_notify` tool-call lives entirely in
  `stream_json.parse`; if the concrete tool transport changes, only the parser adapts. The
  architectural contract is the `notification` `AgentEvent` + dispatcher.
- **Duplicate gate notifications on resume** — a resumed stage re-emitting `gate_opened` must
  not stack inbox items; guard with an idempotency check (one open action-required
  notification per `(run_id, action.kind)`), covered by a test.
- **Scope creep toward blocking gates** — explicitly out of scope; the spec keeps agent
  notifications non-blocking so the Temporal control flow is untouched.

## 14. Cross-references

- **A5d (usage tracking)** provides the spend read a future budget-threshold `alert` will use;
  the producer seam exists here but stays inert until A5d + a configured threshold (phase C).
- A dedicated **dynamic-gate** spec (agent pauses to ask the user) builds on this inbox plus
  new Temporal signal plumbing — deferred.
