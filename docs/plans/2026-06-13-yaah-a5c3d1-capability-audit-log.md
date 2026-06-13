# A5c-3d-1 — Capability audit log — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record a per-stage `capability_granted` audit event (effective tools/skills/mcp/model, never secret values) into an append-only `audit_events` table, viewable via `GET /runs/{id}/audit`.

**Architecture:** A new owner-scoped `audit_events` entity mirroring `run_events`; the `run_stage` activity records the audit event in-process after assembling the agent manifest (best-effort, no worker registration needed); a hand-written audit list route on the runs router.

**Tech Stack:** Python 3.12 · SQLAlchemy · FastAPI · Temporal · pytest.

**Spec:** `docs/specs/2026-06-13-a5c3d1-capability-audit-log-design.md`

**Precondition:** A1–A5c-3b-1 merged to `main`. Mirror `run_events`: `RunEvent`/`RunEventType` (`domain/models.py`), `RunEventRow` (`orm.py`), `RunEventRepository` (`repositories.py`), `uow.run_events` (`uow.py`), `UnitOfWork.run_events` (`ports.py`), `GET /runs/{id}/events` (`routes/runs.py`), `RunActivities.record_event` + its in-process use in `run_stage` (`activities.py`).

## Conventions
- TDD; `uv run pytest <path> -v`; `rm -rf ui/dist` before the full suite; commit per task.
- Audit recording is **best-effort** (a failure never fails the stage) and **never** contains secret values.
- The audit recorder is an **in-process** helper called from `run_stage` (not a registered Temporal activity), so `worker.build_activities` is untouched — avoiding overlap with the in-flight budgets work.

## Parallel waves
- **Wave 1 (one lane — shared persistence files):** PERSIST = T1 (domain) → T2 (orm/repo/uow/ports).
- **Wave 2 (parallel, disjoint):** ACTIVITY = T3 (`activities.py`) ‖ API = T4 (`routes/runs.py`).
- **Wave 3:** T5 verify + integration PR.

---

## Task T1: AuditEvent domain model  (Lane PERSIST)

**Files:** Modify `src/domain/models.py`; Test `tests/unit/test_models.py`.

- [ ] **Step 1: failing test**
```python
def test_audit_event_model():
    from domain.models import AuditAction, AuditEvent, RunStage
    ev = AuditEvent(run_id="r1", owner_id="u", stage=RunStage.IMPLEMENT, actor="backend",
                    action=AuditAction.CAPABILITY_GRANTED,
                    detail={"tools": ["Read"], "model_alias": "engineer-model"})
    assert ev.id and ev.created_at
    assert ev.action == "capability_granted"
    assert ev.detail["tools"] == ["Read"]
```

- [ ] **Step 2: red** → `uv run pytest tests/unit/test_models.py -k audit_event -v` (ImportError).

- [ ] **Step 3: implement** — add to `src/domain/models.py` (near `RunEvent`):
```python
class AuditAction(StrEnum):
    CAPABILITY_GRANTED = "capability_granted"


class AuditEvent(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    run_id: str
    stage: RunStage | None = None
    actor: str = ""
    action: AuditAction
    detail: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
```

- [ ] **Step 4: green** → PASS.
- [ ] **Step 5: commit**
```bash
git add src/domain/models.py tests/unit/test_models.py
git commit -m "feat: AuditEvent + AuditAction domain model"
```

---

## Task T2: audit_events persistence  (Lane PERSIST)

**Files:** Modify `src/adapters/database/orm.py`, `repositories.py`, `uow.py`, `ports.py`; Test `tests/unit/test_repositories.py`.

- [ ] **Step 1: failing test**
```python
def test_audit_events_owner_scoped():
    from adapters.database.engine import make_engine, make_session_factory
    from adapters.database.orm import Base
    from adapters.database.uow import SqlUnitOfWork
    from domain.models import AuditAction, AuditEvent, RunStage

    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        uow.audit_events.create(AuditEvent(run_id="r1", owner_id="u1", stage=RunStage.PLAN,
                                           actor="lead", action=AuditAction.CAPABILITY_GRANTED,
                                           detail={"tools": ["Read"]}))
        page = uow.audit_events.list(filters={"run_id": "r1"})
    assert page.total == 1 and page.results[0].detail["tools"] == ["Read"]
    other = SqlUnitOfWork(factory, required_filters={"owner_id": "u2"})
    with other.transaction():
        assert other.audit_events.list(filters={"run_id": "r1"}).total == 0
```

- [ ] **Step 2: red** → AttributeError (`uow.audit_events`).

- [ ] **Step 3: implement**

`orm.py` (reuse imports `String, Text, JSON, DateTime, Mapped, mapped_column`):
```python
class AuditEventRow(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    stage: Mapped[str | None] = mapped_column(String(30))
    actor: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

`repositories.py` (add imports `AuditEventRow`, `AuditEvent`):
```python
class AuditEventRepository(SqlRepository[AuditEvent]):
    orm_model = AuditEventRow
    dto = AuditEvent
    default_order_by = "created_at"
```

`uow.py` (import `AuditEventRepository`; add property):
```python
    @property
    def audit_events(self) -> AuditEventRepository:
        return AuditEventRepository(self.session, self._required_filters)
```

`ports.py` (import `AuditEvent`; add to `UnitOfWork` Protocol):
```python
    @property
    def audit_events(self) -> Repository[AuditEvent]: ...
```

- [ ] **Step 4: green** → PASS.
- [ ] **Step 5: commit**
```bash
git add src/adapters/database/orm.py src/adapters/database/repositories.py src/adapters/database/uow.py src/adapters/database/ports.py tests/unit/test_repositories.py
git commit -m "feat: audit_events table, repository, UoW property, port"
```

---

## Task T3: run_stage records a capability audit event  (Lane ACTIVITY, wave 2)

**Files:** Modify `src/interactors/temporal/activities.py`; Test `tests/unit/test_activities.py`.

> Needs T1+T2. Touches only `activities.py` (in-process helper — no worker registration).

- [ ] **Step 1: failing test** — assert the event is recorded and carries no secret value:
```python
def test_run_stage_records_capability_audit_without_secret_values():
    import json, tempfile
    from cryptography.fernet import Fernet
    from adapters.database.uow import SqlUnitOfWork
    from adapters.git.fake import FakeGit
    from adapters.forge.fake import FakeGitForge
    from adapters.secrets.cipher import FernetCipher
    from adapters.storage.local import LocalStorageAdapter
    from domain.models import AgentDefinition, Secret, Team
    from interactors.temporal.activities import RunActivities

    factory = _factory()
    run_id = _seed_run(factory)
    cipher = FernetCipher(Fernet.generate_key().decode())
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        team = uow.teams.create(Team(owner_id="u1", name="T"))
        sec = uow.secrets.create(Secret(owner_id="u1", name="GH",
                                        encrypted_value=cipher.encrypt("ghp_SECRET")))
        uow.agents.create(AgentDefinition(team_id=team.id, role="backend", name="E",
                                          model_alias="engineer-model", allowed_tools=["Read", "Edit"],
                                          secret_ids=[sec.id]))

    class _Spy:
        def run_stage(self, ctx):
            from domain.runtime import AgentEvent, StageResult
            yield AgentEvent(type="result", stage=ctx.stage, message="ok",
                             data=StageResult(outcome="ok").model_dump())
        def cancel(self, run_id): ...

    acts = RunActivities(factory, _Spy(), LocalStorageAdapter(base_dir=tempfile.mkdtemp()),
                         FakeGit(), FakeGitForge(), cipher=cipher)
    acts.run_stage({"run_id": run_id, "owner_id": "u1", "stage": "implement",
                    "task_title": "T", "acceptance_criteria": [], "team_id": team.id})

    uow2 = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow2.transaction():
        events = uow2.audit_events.list(filters={"run_id": run_id}).results
    assert len(events) == 1
    detail = events[0].detail
    assert detail["tools"] == ["Read", "Edit"] and detail["model_alias"] == "engineer-model"
    assert detail["secret_count"] == 1
    assert "ghp_SECRET" not in json.dumps(detail)   # no secret value in the audit
```
> Adapt `_factory`/`_seed_run`/`RunActivities` builder to the file's existing helpers.

- [ ] **Step 2: red** → no audit event recorded.

- [ ] **Step 3: implement** — in `src/interactors/temporal/activities.py`:
  - add a helper (plain method, NOT decorated — called in-process):
    ```python
    def _record_audit(self, owner_id: str, run_id: str, stage: str, actor: str, detail: dict) -> None:
        from domain.models import AuditAction, AuditEvent, RunStage, utc_now
        try:
            uow = self._uow(owner_id)
            with uow.transaction():
                uow.audit_events.create(AuditEvent(
                    run_id=run_id, owner_id=owner_id,
                    stage=RunStage(stage) if stage else None,
                    actor=actor, action=AuditAction.CAPABILITY_GRANTED,
                    detail=detail, created_at=utc_now(),
                ))
        except Exception:  # noqa: BLE001 - audit is best-effort, never fails the stage
            pass
    ```
  - in `run_stage`, after `agent_manifest` is assembled (the C2/C3a block) and before calling the
    runtime, record the audit when a manifest exists:
    ```python
            if agent_manifest is not None:
                self._record_audit(
                    payload["owner_id"], payload["run_id"], payload["stage"],
                    selected.role,
                    {
                        "tools": list(agent_manifest.allowed_tools),
                        "skills": [s.name for s in agent_manifest.skills],
                        "mcp_servers": [m.name for m in agent_manifest.mcp_servers],
                        "model_alias": agent_manifest.model_alias,
                        "secret_count": len(agent_manifest.secret_env),
                    },
                )
    ```
    (`selected` is the agent chosen by `capabilities.select_agent` in the same block; reference it
    there. Never put `agent_manifest.secret_env` values into `detail`.)

- [ ] **Step 4: green** → `uv run pytest tests/unit/test_activities.py -v` PASS (existing run_stage tests unaffected — no team/agent → no audit).
- [ ] **Step 5: commit**
```bash
git add src/interactors/temporal/activities.py tests/unit/test_activities.py
git commit -m "feat: run_stage records a capability_granted audit event"
```

---

## Task T4: GET /runs/{id}/audit  (Lane API, wave 2)

**Files:** Modify `src/interactors/api/routes/runs.py`; Test `tests/integration/test_runs_api.py`.

> Needs T2. Touches only `routes/runs.py`.

- [ ] **Step 1: failing test** — seed an audit event then read it:
```python
def test_list_run_audit():
    c, _fake = _client_with_fake_temporal()
    run_id = _seed_awaiting_run(c)   # existing helper that seeds a run for owner dev-user
    from adapters.database.uow import SqlUnitOfWork
    from domain.models import AuditAction, AuditEvent, RunStage
    uow = SqlUnitOfWork(c.app.state.session_factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        uow.audit_events.create(AuditEvent(run_id=run_id, owner_id="dev-user", stage=RunStage.PLAN,
                                           actor="lead", action=AuditAction.CAPABILITY_GRANTED,
                                           detail={"tools": ["Read"]}))
    resp = c.get(f"/runs/{run_id}/audit")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1 and data[0]["action"] == "capability_granted"


def test_audit_unknown_run_404():
    c, _fake = _client_with_fake_temporal()
    assert c.get("/runs/deadbeef/audit").status_code == 404
```
> Use the file's existing client/seed helpers (`_client_with_fake_temporal`, `_seed_awaiting_run`);
> adapt names if they differ.

- [ ] **Step 2: red** → 404 route missing / wrong.

- [ ] **Step 3: implement** — add to `src/interactors/api/routes/runs.py` (mirror `list_run_events`):
```python
@router.get("/runs/{run_id}/audit")
def list_run_audit(run_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        uow.runs.get(run_id)  # 404 if unknown / cross-tenant
        page = uow.audit_events.list(filters={"run_id": run_id}, order_by="created_at", page_size=200)
    return ok([e.model_dump(mode="json") for e in page.results],
              meta={"total": page.total, "page_size": page.page_size, "page_number": page.page_number})
```

- [ ] **Step 4: green** → `uv run pytest tests/integration/test_runs_api.py -k audit -v` PASS.
- [ ] **Step 5: commit**
```bash
git add src/interactors/api/routes/runs.py tests/integration/test_runs_api.py
git commit -m "feat: GET /runs/{id}/audit endpoint"
```

---

## Task T5: Full verify + integration PR  (Wave 3)

- [ ] **Step 1:** `rm -rf ui/dist && uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=80` → all pass, ≥80%.
- [ ] **Step 2:** `uv run ruff check src tests` → clean.
- [ ] **Step 3:** Commit fixes; open the integration PR to `main`.

---

## Self-review (resolved)

- **Spec §4 entity/persistence** ↔ T1 (DTO+enum), T2 (orm/repo/uow/ports). ✅
- **Spec §4 activity recording** ↔ T3 (in-process `_record_audit` from `run_stage`, effective capabilities, secret-safe). ✅
- **Spec §4 API** ↔ T4 (`GET /runs/{id}/audit`). ✅
- **Spec §5 error handling** ↔ best-effort try/except (T3); owner-scoped 404 (T4). ✅
- **Spec §6 testing** ↔ repo owner-scope (T2), activity records + no-secret-value assertion (T3), endpoint + 404 (T4); existing 180 green (no team → no audit). ✅
- **Type consistency:** `AuditEvent`/`AuditAction` defined T1, used in repo (T2), activity (T3), API (T4); `uow.audit_events` consistent T2↔T3↔T4; `detail` keys (`tools/skills/mcp_servers/model_alias/secret_count`) set T3, asserted T3 test. ✅
- **No worker.py / no budgets overlap:** audit recorder is in-process (not a registered activity); `run_stage` change is localized; `worker.build_activities` untouched. ✅
```
