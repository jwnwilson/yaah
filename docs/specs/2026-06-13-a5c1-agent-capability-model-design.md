# yaah A5c-1 (C1) — Agent capability model + grants (Design)

**Date:** 2026-06-13
**Status:** Approved design, pending implementation plan
**Phase:** A5c-1 (first slice of A5c hardening — the capability foundation)
**Depends on:** A1–A5b (all merged to `main`).

## 1. Problem & goal

Agents are configured too thinly: `AgentDefinition` is just `role, name, persona, model_alias,
runtime`, and the pipeline runs stages generically. To control what a real agent can do, each
agent needs its own **purpose, system prompt, and an explicit set of granted skills / MCP servers
/ tools / secrets**, persisted in Postgres and managed via the API. C1 builds that **data model +
grants + management API** — the foundation the runtime later composes from (C2) and that secrets
injection + audit build on (C3). Deny-by-default falls out naturally: an agent only has what it's
granted.

### C1 success criterion

> Through the API I can create owner-scoped Skill, McpServer, and Secret registry entries, create
> an agent under a team with a purpose, system prompt, an allowed-tools list, and grant references
> to those registry entries, and read it back — with grant references to non-existent or
> cross-tenant entries rejected. The default team's agents come pre-populated with per-role
> purpose/system-prompt/tools.

## 2. Scope

### In scope
- **Registry entities** (owner-scoped): `Skill`, `McpServer`, `Secret` (reference only — no value yet).
- **`AgentDefinition` extension**: `purpose`, `system_prompt`, `allowed_tools`, `skill_ids`,
  `mcp_server_ids`, `secret_ids` (JSON id-lists referencing registry rows).
- **Persistence** for the new entities + agent columns (ORM, repository, UoW, ports).
- **Management API**: CrudRouter for `/skills`, `/mcp-servers`, `/secrets`; **agent CRUD** under a
  team; grant-reference validation (existence + owner scope) on agent create/update.
- **Default team** factory sets per-role purpose/system_prompt/allowed_tools.

### Out of scope (later)
- Runtime *using* grants (system prompt/tools/skills/MCP attachment) — **C2**.
- Per-stage agent selection (role↔stage) — **C2**.
- Secret **values + encryption + injection** + capability/tool **audit log** — **C3** (with the
  egress broker).
- Board registry/agent UIs — phase C.
- Normalized join tables (we use JSON id-lists), RAG indexes/ModelAlias registry (phase B/C).

## 3. Decisions log

| Decision | Choice | Rationale |
|---|---|---|
| Registries | **First-class owner-scoped tables** (Skill/McpServer/Secret) | Matches spec §9 + eventual board UIs; central management |
| Grant storage | **JSON id-lists on `AgentDefinition`** | Same pattern as `acceptance_criteria`; simpler than join tables; YAGNI |
| Secret value | **Deferred to C3** (reference only in C1) | Don't store plaintext before encryption exists |
| Tools | **`allowed_tools: list[str]`** on the agent (claude built-ins) | Tools are runtime built-ins, not a registry |
| Agent management | **New agent CRUD API** | Today agents only exist via `POST /teams/default` |
| Grant validation | **At agent create/update**, in the route via UoW lookups | Fail fast; reuse owner-scoped repos |

## 4. Domain model (`src/domain/models.py`)

```python
class Skill(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    name: str
    description: str = ""
    source: str = ""            # git URL or path to the SKILL.md folder
    created_at: datetime = Field(default_factory=utc_now)

class McpServer(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    name: str
    transport: Literal["stdio", "http"] = "stdio"
    command_or_url: str = ""
    tool_allowlist: list[str] = Field(default_factory=list)  # mcp__server__tool
    created_at: datetime = Field(default_factory=utc_now)

class Secret(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    name: str
    description: str = ""
    created_at: datetime = Field(default_factory=utc_now)
    # value + encryption are C3; never stored/returned here

# AgentDefinition gains:
    purpose: str = ""
    system_prompt: str = ""
    allowed_tools: list[str] = Field(default_factory=list)
    skill_ids: list[str] = Field(default_factory=list)
    mcp_server_ids: list[str] = Field(default_factory=list)
    secret_ids: list[str] = Field(default_factory=list)
```

## 5. Persistence (architecture "adding an entity" checklist)

For each of Skill / McpServer / Secret:
1. Domain DTO (above).
2. ORM row in `adapters/database/orm.py` (`id`, `owner_id` indexed, columns incl. `JSON` for
   `tool_allowlist`, `created_at`).
3. Repository subclass in `repositories.py` (`orm_model`, `dto`).
4. UoW property in `uow.py` (`skills`, `mcp_servers`, `secrets`).
5. Protocol entry in `adapters/database/ports.py`.

`AgentDefinitionRow` gains: `purpose` (Text), `system_prompt` (Text), `allowed_tools` (JSON),
`skill_ids` (JSON), `mcp_server_ids` (JSON), `secret_ids` (JSON). `AgentDefinition` repo already
exists. `create_all` picks up the new tables/columns (alembic still deferred).

## 6. API (`interactors/api/routes/`)

- **Registries** via `CrudRouter` (owner-scoped, enveloped, paginated) — `capabilities.py`:
  `/skills`, `/mcp-servers`, `/secrets` with `CREATE/READ/UPDATE/DELETE`.
- **Agents** — `agents.py` (UoW-based, mirrors `work_items` route style):
  - `POST /teams/{team_id}/agents` (201) — validates `team_id` exists/owner-scoped; creates the agent.
  - `GET /teams/{team_id}/agents` (paginated list).
  - `GET /agents/{id}`, `PATCH /agents/{id}`, `DELETE /agents/{id}`.
  - **Grant validation** helper: for each `skill_ids`/`mcp_server_ids`/`secret_ids`, `uow.<repo>.get(id)`
    (owner-scoped) — any miss → `RecordNotFound` → 404 (or 422 with a clear message). `allowed_tools`
    is free-form strings (no registry).
- Agent owner scoping: `AgentDefinition` has **no `owner_id`** (reached via its owner-scoped team).
  Agent routes resolve/validate the parent team via the owner-scoped `uow.teams` first, exactly as
  work-item routes validate the project.

## 7. Default team (`domain/teams.py`)

Extend `default_team` so each starter agent carries a per-role `purpose`, `system_prompt`, and a
conservative `allowed_tools` (e.g. lead: read/plan; engineer: read/edit/write/bash; qa:
read/bash). Empty skill/mcp/secret grants. Update the existing team test accordingly.

## 8. Error handling

- Grant references to missing/cross-tenant entries → `RecordNotFound` → 404 (uniform with the rest
  of the API). Bad `transport`/enum → `ValidationError` → 422 (domain validators).
- All registry/agent writes go through the UoW transaction; envelope + exception handlers already
  map errors.

## 9. Testing (80% gate)

- **Repository units** (SQLite in-memory): create/list/owner-scope for Skill/McpServer/Secret;
  AgentDefinition round-trips the new JSON grant fields.
- **Integration (API)**: registry CRUD (owner-scoped, 404 cross-tenant); agent CRUD under a team;
  grant validation (404 on a bogus skill/mcp/secret id); default-team agents expose
  purpose/system_prompt/tools.
- **Domain**: `default_team` per-role fields.

## 10. Risks

- **JSON id-lists vs join tables** — no FK enforcement; mitigated by create/update validation. If
  referential integrity becomes load-bearing (phase C), migrate to join tables.
- **Secret without a value** is inert in C1 — intentional; it reserves the name/reference so C3 can
  add encrypted values + injection without reshaping grants.
- **Agent CRUD is new surface** — keep it thin (wiring only), validation in the route, business
  rules (hierarchy: agent requires a team) in the domain model validator.
