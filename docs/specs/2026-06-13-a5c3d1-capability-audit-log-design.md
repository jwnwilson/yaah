# yaah A5c-3d-1 (C3d-1) — Capability audit log (Design)

**Date:** 2026-06-13
**Status:** Approved design, pending implementation plan
**Phase:** A5c-3d-1 (passive audit foundation; active PreToolUse interceptor is C3d-2)
**Depends on:** A1–A5c-3a + C3b-1 (all merged to `main`). Note: C3b-2 (budgets) is in flight on another branch and also touches `run_stage`; the second to merge may need a trivial rebase.

## 1. Problem & goal

The spec (§7) requires every capability/tool decision to land in an **append-only audit log,
viewable per run**. C2 makes deny-by-default real (an agent only gets granted tools/skills/MCP),
but nothing records *what each stage's agent was permitted*. C3d-1 adds an append-only
`audit_events` table and records a per-stage **capability audit event** when the runtime composes
the agent — giving a reviewable per-run audit trail. Secret **values are never recorded** (names
and counts only). The active PreToolUse interceptor (auditing every actual tool call) is C3d-2.

### C3d-1 success criterion

> After a run, `GET /runs/{id}/audit` returns one `capability_granted` event per agent stage,
> each showing the agent role, the effective `allowed_tools`, the granted skill/MCP names, and the
> `model_alias` — with **no** secret values anywhere. Cross-tenant audit reads 404.

## 2. Scope

### In scope
- **`AuditEvent`** entity + append-only `audit_events` table (owner-scoped), repository, UoW prop, ports.
- The `run_stage` activity records a `capability_granted` audit event (effective tools/skills/MCP/model)
  after assembling the agent manifest — **never** secret values.
- **`GET /runs/{id}/audit`** (owner-scoped, paginated).

### Out of scope (later)
- **Active PreToolUse interceptor** auditing real tool calls (**C3d-2**).
- Response/log **redaction** (**C3c**).
- Audit UI / cross-project audit views (phase C).
- Auditing non-agent stages (PROVISION/PR) — they have no agent capabilities.

## 3. Decisions log

| Decision | Choice | Rationale |
|---|---|---|
| Pattern | **Mirror `run_events`** (append-only, owner-scoped table) | Proven; consistent |
| What's recorded | per-stage **effective capability manifest** (role, tools, skill/mcp names, model_alias) | "What the agent was permitted" — reviewable, deny-by-default visible |
| Secret safety | **names/counts only, never values** | Audit must not leak secrets (tested) |
| Where recorded | in the `run_stage` activity, after manifest assembly | The activity already has the manifest in-process |
| Action enum | `capability_granted` now | room for `tool_allowed`/`tool_denied` in C3d-2 |

## 4. Architecture

```
src/
  domain/models.py            # AuditEvent DTO + AuditAction enum
  adapters/database/
    orm.py                    # AuditEventRow
    repositories.py           # AuditEventRepository
    uow.py                    # uow.audit_events
    ports.py                  # UnitOfWork.audit_events
  interactors/temporal/activities.py  # run_stage records a capability_granted audit event
  interactors/api/routes/runs.py      # GET /runs/{id}/audit
```

### Domain
```python
class AuditAction(StrEnum):
    CAPABILITY_GRANTED = "capability_granted"

class AuditEvent(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    run_id: str
    stage: RunStage | None = None
    actor: str = ""                 # agent role (e.g. "backend")
    action: AuditAction
    detail: dict = Field(default_factory=dict)   # {tools, skills, mcp_servers, model_alias} — no secret values
    created_at: datetime = Field(default_factory=utc_now)
```

### Persistence
`AuditEventRow` (`id, owner_id` idx, `run_id` idx, `stage`, `actor`, `action`, `detail` JSON,
`created_at`); `AuditEventRepository(SqlRepository[AuditEvent])`; `uow.audit_events`; ports entry.
Append-only (never updated). `create_all` picks it up.

### Activity recording
In `run_stage`, after the C2 block assembles `agent_manifest` (and C3a populates `secret_env`),
record one audit event **before** running the agent:
```python
if agent_manifest is not None:
    self.record_audit({
        "run_id": payload["run_id"], "owner_id": payload["owner_id"],
        "stage": payload["stage"], "actor": selected.role,
        "action": AuditAction.CAPABILITY_GRANTED,
        "detail": {
            "tools": agent_manifest.allowed_tools,
            "skills": [s.name for s in agent_manifest.skills],
            "mcp_servers": [m.name for m in agent_manifest.mcp_servers],
            "model_alias": agent_manifest.model_alias,
            "secret_count": len(agent_manifest.secret_env),   # COUNT only — never names/values? names ok, values never
        },
    })
```
`record_audit` is a small activity-helper that opens an owner-scoped UoW and creates the row
(parallel to `record_event`). **`detail` must never include `secret_env` values** — only the count
(secret *names* may be included if desired, but values never). Tests assert no value leaks.

### API
`GET /runs/{run_id}/audit` (in `routes/runs.py`, mirrors `/runs/{id}/events`): owner-scoped
`uow.runs.get` (404 if absent), then `uow.audit_events.list(filters={"run_id": run_id},
order_by="created_at")`, enveloped + paginated meta.

## 5. Error handling
- Audit recording failure must not fail the stage — wrap in a try/except that logs (no secret) and
  continues (audit is best-effort observability, not a gate).
- Owner scoping via required filters; cross-tenant `GET /runs/{id}/audit` → 404 (run not found).

## 6. Testing (80% gate)
- **Repo unit:** create/list `audit_events`, owner-scoping (cross-tenant hidden).
- **Activity:** with a seeded team/agent (+ a granted secret with a value), `run_stage` records a
  `capability_granted` event whose `detail` has tools/skills/mcp/model and **does not contain the
  secret value** (assert the plaintext absent from the recorded payload).
- **API:** `GET /runs/{id}/audit` returns the events; cross-tenant → 404.
- Existing 180 tests green (no agent/team → no audit event; additive).

## 7. Risks
- **Secret leakage into `detail`** — the single rule (values never, count/names only) is enforced by
  a test asserting absence; reviewers guard it. (Full redaction of agent-echoed secrets is C3c.)
- **Merge overlap with in-flight budgets** — both add to `run_stage`; localized regions, trivial
  rebase for whoever merges second.
- **Volume** — one event per agent stage per run (small); pagination on the endpoint covers growth.
