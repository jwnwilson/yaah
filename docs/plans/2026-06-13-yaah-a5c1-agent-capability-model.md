# A5c-1 — Agent capability model + grants — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist per-agent purpose/system-prompt + granted skills/MCP/tools/secrets in Postgres, with owner-scoped registries and management API, so the runtime (C2) can later compose agent invocations from grants.

**Architecture:** Three owner-scoped registry entities (Skill/McpServer/Secret) added via the existing "adding an entity" checklist; `AgentDefinition` gains `purpose`/`system_prompt` + JSON id-list grants; registry CRUD via `CrudRouter`; new agent CRUD routes under a team with grant-reference validation; `default_team` pre-populates per-role fields.

**Tech Stack:** Python 3.12 · SQLAlchemy (sync) · FastAPI · Pydantic v2 · pytest.

**Spec:** `docs/specs/2026-06-13-a5c1-agent-capability-model-design.md`

**Precondition:** A1–A5b merged to `main`. Patterns to mirror: `domain/models.py` DTOs; `adapters/database/orm.py` rows; `repositories.py` subclasses; `uow.py` properties; `adapters/database/ports.py` Protocol; `lib/crud_router.py` (`CrudRouter`, injects `owner_id` on create); route style in `routes/projects.py` (CrudRouter) + `routes/work_items.py`/`routes/teams.py` (UoW hand-written).

## Conventions
- TDD; `uv run pytest <path> -v`; `rm -rf ui/dist` before the full suite; commit per task with the given message.
- Owner scoping: owned rows carry `owner_id` (CrudRouter injects it); `AgentDefinition` has **no** `owner_id` (reached via its owner-scoped team), matching today.

## Parallel waves
- **Wave 1 (one lane — shared persistence files):** Lane PERSIST = T1 (models) → T2 (orm) → T3 (repos/uow/ports).
- **Wave 2 (parallel, disjoint):** Lane DEFAULT-TEAM = T4 ‖ Lane API = T5 (registries) → T6 (agents).
- **Wave 3:** T7 verify + integration PR.

---

## Task T1: Domain models (registries + AgentDefinition grants)  (Lane PERSIST)

**Files:** Modify `src/domain/models.py`; Test `tests/unit/test_models.py`.

- [ ] **Step 1: failing test** — add:
```python
def test_capability_models_and_agent_grants():
    from domain.models import Skill, McpServer, Secret, AgentDefinition

    s = Skill(owner_id="u", name="pytest", source="git@x/skills.git")
    m = McpServer(owner_id="u", name="fs", transport="stdio", command_or_url="npx mcp-fs",
                  tool_allowlist=["mcp__fs__read"])
    sec = Secret(owner_id="u", name="GH_TOKEN", description="github")
    assert s.id and m.tool_allowlist == ["mcp__fs__read"] and sec.name == "GH_TOKEN"

    a = AgentDefinition(team_id="t", role="lead", name="Lead", model_alias="lead-model",
                        purpose="run the show", system_prompt="You are the lead.",
                        allowed_tools=["Read", "Write"], skill_ids=[s.id],
                        mcp_server_ids=[m.id], secret_ids=[sec.id])
    assert a.purpose == "run the show" and a.skill_ids == [s.id]
    assert a.allowed_tools == ["Read", "Write"]
```

- [ ] **Step 2: red** → `uv run pytest tests/unit/test_models.py -k capability_models -v` (ImportError/TypeError).

- [ ] **Step 3: implement** — in `src/domain/models.py`: ensure `from typing import Literal` is imported; add the three DTOs (place near `Team`/`AgentDefinition`):
```python
class Skill(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    name: str
    description: str = ""
    source: str = ""
    created_at: datetime = Field(default_factory=utc_now)


class McpServer(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    name: str
    transport: Literal["stdio", "http"] = "stdio"
    command_or_url: str = ""
    tool_allowlist: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class Secret(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    name: str
    description: str = ""
    created_at: datetime = Field(default_factory=utc_now)
```
and extend `AgentDefinition` with:
```python
    purpose: str = ""
    system_prompt: str = ""
    allowed_tools: list[str] = Field(default_factory=list)
    skill_ids: list[str] = Field(default_factory=list)
    mcp_server_ids: list[str] = Field(default_factory=list)
    secret_ids: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: green** → PASS.
- [ ] **Step 5: commit**
```bash
git add src/domain/models.py tests/unit/test_models.py
git commit -m "feat: Skill/McpServer/Secret DTOs + AgentDefinition grant fields"
```

---

## Task T2: ORM rows + AgentDefinition columns  (Lane PERSIST)

**Files:** Modify `src/adapters/database/orm.py`; Test `tests/unit/test_orm.py`.

- [ ] **Step 1: failing test** — add to `tests/unit/test_orm.py` (mirror its existing create-engine/create_all helper; if it uses a local helper, reuse it):
```python
def test_capability_rows_roundtrip():
    from adapters.database.engine import make_engine, make_session_factory
    from adapters.database.orm import Base, SkillRow, McpServerRow, SecretRow, AgentDefinitionRow

    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = make_session_factory(engine)()
    s.add(SkillRow(id="s1", owner_id="u", name="pytest", description="", source="x",
                   created_at=__import__("datetime").datetime.now()))
    s.add(AgentDefinitionRow(id="a1", team_id="t", role="lead", name="L", persona="",
                             model_alias="m", runtime="claude_code", purpose="p",
                             system_prompt="sp", allowed_tools=["Read"], skill_ids=["s1"],
                             mcp_server_ids=[], secret_ids=[]))
    s.commit()
    assert s.get(SkillRow, "s1").name == "pytest"
    assert s.get(AgentDefinitionRow, "a1").skill_ids == ["s1"]
```

- [ ] **Step 2: red** → ImportError (rows/columns missing).

- [ ] **Step 3: implement** — in `src/adapters/database/orm.py` add rows (reuse existing imports `String, Text, JSON, DateTime, Mapped, mapped_column`):
```python
class SkillRow(Base):
    __tablename__ = "skills"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class McpServerRow(Base):
    __tablename__ = "mcp_servers"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    transport: Mapped[str] = mapped_column(String(10), nullable=False, default="stdio")
    command_or_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    tool_allowlist: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SecretRow(Base):
    __tablename__ = "secrets"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```
and add columns to `AgentDefinitionRow`:
```python
    purpose: Mapped[str] = mapped_column(Text, nullable=False, default="")
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    allowed_tools: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    skill_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    mcp_server_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    secret_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
```

- [ ] **Step 4: green** → PASS.
- [ ] **Step 5: commit**
```bash
git add src/adapters/database/orm.py tests/unit/test_orm.py
git commit -m "feat: capability ORM rows + AgentDefinition grant columns"
```

---

## Task T3: Repositories + UoW + ports  (Lane PERSIST)

**Files:** Modify `src/adapters/database/repositories.py`, `uow.py`, `ports.py`; Test `tests/unit/test_repositories.py`.

- [ ] **Step 1: failing test** — add:
```python
def test_capability_repos_owner_scoped_and_agent_grants():
    from adapters.database.engine import make_engine, make_session_factory
    from adapters.database.orm import Base
    from adapters.database.uow import SqlUnitOfWork
    from domain.models import Skill, AgentDefinition, Team

    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        sk = uow.skills.create(Skill(owner_id="u1", name="pytest"))
        team = uow.teams.create(Team(owner_id="u1", name="T"))
        uow.agents.create(AgentDefinition(team_id=team.id, role="lead", name="L",
                                          model_alias="m", skill_ids=[sk.id]))
        skills_page = uow.skills.list()
        agent = uow.agents.list(filters={"team_id": team.id}).results[0]
    assert skills_page.total == 1 and agent.skill_ids == [sk.id]

    other = SqlUnitOfWork(factory, required_filters={"owner_id": "u2"})
    with other.transaction():
        assert other.skills.list().total == 0   # cross-tenant hidden
```

- [ ] **Step 2: red** → AttributeError (`uow.skills` missing).

- [ ] **Step 3: implement**

`repositories.py` (add imports `McpServerRow, SecretRow, SkillRow` and `McpServer, Secret, Skill`):
```python
class SkillRepository(SqlRepository[Skill]):
    orm_model = SkillRow
    dto = Skill


class McpServerRepository(SqlRepository[McpServer]):
    orm_model = McpServerRow
    dto = McpServer


class SecretRepository(SqlRepository[Secret]):
    orm_model = SecretRow
    dto = Secret
```

`uow.py` (import the three repos; add properties):
```python
    @property
    def skills(self) -> SkillRepository:
        return SkillRepository(self.session, self._required_filters)

    @property
    def mcp_servers(self) -> McpServerRepository:
        return McpServerRepository(self.session, self._required_filters)

    @property
    def secrets(self) -> SecretRepository:
        return SecretRepository(self.session, self._required_filters)
```

`adapters/database/ports.py` (import `McpServer, Secret, Skill`; add to the `UnitOfWork` Protocol):
```python
    @property
    def skills(self) -> Repository[Skill]: ...
    @property
    def mcp_servers(self) -> Repository[McpServer]: ...
    @property
    def secrets(self) -> Repository[Secret]: ...
```

- [ ] **Step 4: green** → PASS.
- [ ] **Step 5: commit**
```bash
git add src/adapters/database/repositories.py src/adapters/database/uow.py src/adapters/database/ports.py tests/unit/test_repositories.py
git commit -m "feat: capability repositories + UoW properties + ports"
```

---

## Task T4: default_team per-role fields  (Lane DEFAULT-TEAM, wave 2)

**Files:** Modify `src/domain/teams.py`; Test `tests/unit/test_teams.py`.

> Needs T1 (AgentDefinition fields). Independent of the API lane (different files).

- [ ] **Step 1: failing test** — add to `tests/unit/test_teams.py`:
```python
def test_default_team_agents_have_purpose_and_tools():
    from domain.teams import default_team
    _team, agents = default_team(owner_id="u")
    by_role = {a.role: a for a in agents}
    assert all(a.purpose and a.system_prompt for a in agents)
    assert "Read" in by_role["lead"].allowed_tools
    assert "Edit" in by_role["backend"].allowed_tools
    assert "Edit" not in by_role["qa"].allowed_tools  # QA is read-only
```

- [ ] **Step 2: red** → AssertionError (fields empty).

- [ ] **Step 3: implement** — rewrite `_DEFAULT_AGENTS` + factory in `src/domain/teams.py`:
```python
from domain.models import AgentDefinition, AgentRole, Team

# role, name, model alias, purpose, system prompt, allowed tools
_DEFAULT_AGENTS: list[tuple[AgentRole, str, str, str, str, list[str]]] = [
    (AgentRole.LEAD, "Lead", "lead-model",
     "Plan the work and coordinate the team.",
     "You are the team lead. Read the ticket and produce a clear implementation plan.",
     ["Read", "Write"]),
    (AgentRole.BACKEND, "Engineer", "engineer-model",
     "Implement the ticket in the repository.",
     "You are a senior engineer. Implement the ticket and keep changes focused.",
     ["Read", "Edit", "Write", "Bash"]),
    (AgentRole.QA, "QA", "qa-model",
     "Verify the implementation against the acceptance criteria.",
     "You are QA. Adversarially verify the work; run tests; do not modify source.",
     ["Read", "Bash"]),
]


def default_team(owner_id: str, name: str = "Default Team") -> tuple[Team, list[AgentDefinition]]:
    """The Phase-A starter team: lead + engineer + QA (spec §10)."""
    team = Team(owner_id=owner_id, name=name)
    agents = [
        AgentDefinition(team_id=team.id, role=role, name=agent_name, model_alias=alias,
                        purpose=purpose, system_prompt=system_prompt, allowed_tools=tools)
        for role, agent_name, alias, purpose, system_prompt, tools in _DEFAULT_AGENTS
    ]
    return team, agents
```

- [ ] **Step 4: green** → `uv run pytest tests/unit/test_teams.py -v` PASS.
- [ ] **Step 5: commit**
```bash
git add src/domain/teams.py tests/unit/test_teams.py
git commit -m "feat: default team agents carry purpose/system-prompt/tools"
```

---

## Task T5: Registry CRUD routes  (Lane API, wave 2)

**Files:** Create `src/interactors/api/routes/capabilities.py`; Modify `src/interactors/api/app.py`; Test `tests/integration/test_capabilities_api.py`.

> Needs T3 (uow props). Same lane as T6.

- [ ] **Step 1: failing test**
```python
# tests/integration/test_capabilities_api.py
from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings


def _client():
    return TestClient(create_app(Settings(_env_file=None, database_url="sqlite:///:memory:")))


def test_skill_crud_owner_scoped():
    c = _client()
    r = c.post("/skills", json={"name": "pytest", "source": "git@x/s.git"})
    assert r.status_code == 201
    sid = r.json()["data"]["id"]
    assert c.get(f"/skills/{sid}").status_code == 200
    assert c.get("/skills").json()["meta"]["total"] == 1


def test_mcp_and_secret_create():
    c = _client()
    assert c.post("/mcp-servers", json={"name": "fs", "transport": "stdio",
                  "command_or_url": "npx mcp-fs", "tool_allowlist": ["mcp__fs__read"]}).status_code == 201
    assert c.post("/secrets", json={"name": "GH_TOKEN", "description": "gh"}).status_code == 201
```

- [ ] **Step 2: red** → 404 (routes absent).

- [ ] **Step 3: implement** `src/interactors/api/routes/capabilities.py`:
```python
from typing import Literal

from pydantic import BaseModel

from domain.models import McpServer, Secret, Skill
from lib.crud_router import CrudRouter


class CreateSkill(BaseModel):
    name: str
    description: str = ""
    source: str = ""


class UpdateSkill(BaseModel):
    name: str | None = None
    description: str | None = None
    source: str | None = None


class CreateMcpServer(BaseModel):
    name: str
    transport: Literal["stdio", "http"] = "stdio"
    command_or_url: str = ""
    tool_allowlist: list[str] = []


class UpdateMcpServer(BaseModel):
    name: str | None = None
    transport: Literal["stdio", "http"] | None = None
    command_or_url: str | None = None
    tool_allowlist: list[str] | None = None


class CreateSecret(BaseModel):
    name: str
    description: str = ""


class UpdateSecret(BaseModel):
    name: str | None = None
    description: str | None = None


skills_router = CrudRouter(repository="skills", response_dto=Skill,
                           create_schema=CreateSkill, update_schema=UpdateSkill,
                           methods=("CREATE", "READ", "UPDATE", "DELETE"),
                           prefix="/skills", tags=["capabilities"])
mcp_router = CrudRouter(repository="mcp_servers", response_dto=McpServer,
                        create_schema=CreateMcpServer, update_schema=UpdateMcpServer,
                        methods=("CREATE", "READ", "UPDATE", "DELETE"),
                        prefix="/mcp-servers", tags=["capabilities"])
secrets_router = CrudRouter(repository="secrets", response_dto=Secret,
                            create_schema=CreateSecret, update_schema=UpdateSecret,
                            methods=("CREATE", "READ", "UPDATE", "DELETE"),
                            prefix="/secrets", tags=["capabilities"])
```
In `app.py`, import and include all three (next to the other includes):
```python
    from interactors.api.routes import capabilities
    app.include_router(capabilities.skills_router)
    app.include_router(capabilities.mcp_router)
    app.include_router(capabilities.secrets_router)
```

- [ ] **Step 4: green** → `uv run pytest tests/integration/test_capabilities_api.py -v` PASS.
- [ ] **Step 5: commit**
```bash
git add src/interactors/api/routes/capabilities.py src/interactors/api/app.py tests/integration/test_capabilities_api.py
git commit -m "feat: skill/mcp/secret registry CRUD routes"
```

---

## Task T6: Agent CRUD routes + grant validation  (Lane API, wave 2)

**Files:** Create `src/interactors/api/routes/agents.py`; Modify `src/interactors/api/app.py`; Test `tests/integration/test_agents_api.py`.

- [ ] **Step 1: failing test**
```python
# tests/integration/test_agents_api.py
from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings


def _client():
    return TestClient(create_app(Settings(_env_file=None, database_url="sqlite:///:memory:")))


def _team(c) -> str:
    return c.post("/teams/default").json()["data"]["team"]["id"]


def test_create_agent_with_valid_grants():
    c = _client()
    tid = _team(c)
    sid = c.post("/skills", json={"name": "pytest"}).json()["data"]["id"]
    r = c.post(f"/teams/{tid}/agents", json={
        "role": "backend", "name": "Eng", "model_alias": "m",
        "purpose": "build", "system_prompt": "you build",
        "allowed_tools": ["Read", "Edit"], "skill_ids": [sid]})
    assert r.status_code == 201
    aid = r.json()["data"]["id"]
    assert c.get(f"/agents/{aid}").json()["data"]["skill_ids"] == [sid]


def test_create_agent_with_bogus_grant_is_404():
    c = _client()
    tid = _team(c)
    r = c.post(f"/teams/{tid}/agents", json={"role": "qa", "name": "Q", "model_alias": "m",
               "skill_ids": ["nope"]})
    assert r.status_code == 404


def test_agents_listed_under_team_and_patch():
    c = _client()
    tid = _team(c)
    aid = c.post(f"/teams/{tid}/agents", json={"role": "lead", "name": "L",
                 "model_alias": "m"}).json()["data"]["id"]
    assert c.get(f"/teams/{tid}/agents").json()["meta"]["total"] >= 1
    assert c.patch(f"/agents/{aid}", json={"purpose": "lead it"}).json()["data"]["purpose"] == "lead it"
```

- [ ] **Step 2: red** → 404.

- [ ] **Step 3: implement** `src/interactors/api/routes/agents.py`:
```python
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from adapters.database.ports import UnitOfWork
from domain.models import AgentDefinition, AgentRole
from interactors.api.deps import get_uow
from interactors.api.envelope import ok

router = APIRouter(tags=["agents"])


class CreateAgent(BaseModel):
    role: AgentRole
    name: str
    model_alias: str
    persona: str = ""
    purpose: str = ""
    system_prompt: str = ""
    allowed_tools: list[str] = []
    skill_ids: list[str] = []
    mcp_server_ids: list[str] = []
    secret_ids: list[str] = []


class UpdateAgent(BaseModel):
    name: str | None = None
    model_alias: str | None = None
    persona: str | None = None
    purpose: str | None = None
    system_prompt: str | None = None
    allowed_tools: list[str] | None = None
    skill_ids: list[str] | None = None
    mcp_server_ids: list[str] | None = None
    secret_ids: list[str] | None = None


def _validate_grants(uow: UnitOfWork, skill_ids, mcp_server_ids, secret_ids) -> None:
    for sid in skill_ids or []:
        uow.skills.get(sid)            # RecordNotFound -> 404 (owner-scoped)
    for mid in mcp_server_ids or []:
        uow.mcp_servers.get(mid)
    for sec in secret_ids or []:
        uow.secrets.get(sec)


@router.post("/teams/{team_id}/agents", status_code=201)
def create_agent(team_id: str, body: CreateAgent, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        uow.teams.get(team_id)  # 404 if team absent / not owned
        _validate_grants(uow, body.skill_ids, body.mcp_server_ids, body.secret_ids)
        agent = AgentDefinition(team_id=team_id, **body.model_dump())
        created = uow.agents.create(agent)
    return ok(created.model_dump(mode="json"))


@router.get("/teams/{team_id}/agents")
def list_agents(team_id: str, page_size: int = Query(100, ge=1, le=200),
                page_number: int = Query(1, ge=1), uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        uow.teams.get(team_id)
        page = uow.agents.list(filters={"team_id": team_id}, page_size=page_size,
                               page_number=page_number, order_by="id")
    return ok([a.model_dump(mode="json") for a in page.results],
              meta={"total": page.total, "page_size": page.page_size, "page_number": page.page_number})


@router.get("/agents/{agent_id}")
def get_agent(agent_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        agent = uow.agents.get(agent_id)
    return ok(agent.model_dump(mode="json"))


@router.patch("/agents/{agent_id}")
def patch_agent(agent_id: str, body: UpdateAgent, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        agent = uow.agents.get(agent_id)
        updates = body.model_dump(exclude_none=True)
        _validate_grants(uow, updates.get("skill_ids"), updates.get("mcp_server_ids"),
                         updates.get("secret_ids"))
        result = uow.agents.update(agent_id, agent.model_copy(update=updates))
    return ok(result.model_dump(mode="json"))


@router.delete("/agents/{agent_id}")
def delete_agent(agent_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        uow.agents.delete(agent_id)
    return ok({"deleted": agent_id})
```
> Note: `uow.agents` (the `AgentDefinitionRepository`) is **not owner-scoped** (no `owner_id` column); `get(agent_id)` returns any agent. Owner scoping is enforced by resolving the parent **team** through the owner-scoped `uow.teams` in create/list. `GET/PATCH/DELETE /agents/{id}` are acceptable for single-user A-phase; a later phase can join through team for strict cross-tenant agent isolation (note it, don't build it now).

In `app.py` add:
```python
    from interactors.api.routes import agents
    app.include_router(agents.router)
```

- [ ] **Step 4: green** → `uv run pytest tests/integration/test_agents_api.py -v` PASS.
- [ ] **Step 5: commit**
```bash
git add src/interactors/api/routes/agents.py src/interactors/api/app.py tests/integration/test_agents_api.py
git commit -m "feat: agent CRUD routes with grant-reference validation"
```

---

## Task T7: Full verify + integration PR  (Wave 3)

- [ ] **Step 1:** `rm -rf ui/dist && uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=80` → all pass, ≥80%.
- [ ] **Step 2:** `uv run ruff check src tests` → clean.
- [ ] **Step 3:** Commit fixes; open the integration PR to `main`.

---

## Self-review (resolved)

- **Spec §4 model** ↔ T1 (Skill/McpServer/Secret + AgentDefinition fields). ✅
- **Spec §5 persistence** ↔ T2 (rows/columns), T3 (repos/uow/ports). ✅
- **Spec §6 API** ↔ T5 (registry CrudRouters), T6 (agent CRUD + grant validation + app includes). ✅
- **Spec §7 default team** ↔ T4. ✅
- **Spec §8 error handling** ↔ grant validation raises `RecordNotFound`→404 (T6); enum/validation→422 via domain (T1). ✅
- **Spec §9 testing** ↔ repo units (T3), orm roundtrip (T2), model unit (T1), registry+agent integration (T5,T6), default-team (T4). ✅
- **Type consistency:** field names `purpose/system_prompt/allowed_tools/skill_ids/mcp_server_ids/secret_ids` identical across DTO (T1), ORM columns (T2), default_team (T4), and route schemas (T6); repo names `skills/mcp_servers/secrets` identical across uow (T3), ports (T3), CrudRouter `repository=` (T5), and grant validation (T6). ✅
- **Secret value** intentionally absent (C3). `AgentDefinition` stays without `owner_id` (team-scoped), consistent with today. ✅
```
