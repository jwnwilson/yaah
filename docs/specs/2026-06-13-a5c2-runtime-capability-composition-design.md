# yaah A5c-2 (C2) — Runtime composes per-stage agent grants (Design)

**Date:** 2026-06-13
**Status:** Approved design, pending implementation plan
**Phase:** A5c-2 (second slice of A5c)
**Depends on:** A1–A5b + A5c-1 (all merged to `main`) — AgentDefinition grants + Skill/McpServer/Secret registries; ClaudeCodeRuntime; domain/prompts.py; pipeline.

## 1. Problem & goal

A5c-1 stores per-agent purpose/system_prompt + grants (skills/MCP/tools/secrets), but the runtime
ignores them: every stage runs with a static prompt + tool list. C2 makes the pipeline **select
the right agent per stage** and have `ClaudeCodeRuntime` **compose the `claude` invocation from
that agent's grants** — system prompt, allowed tools, granted skills (cloned/mounted), and granted
MCP servers. Deny-by-default becomes real: an agent only gets what it's granted. Secret *values* +
injection and the audit log remain C3.

### C2 success criterion

> A run uses the team's **lead** agent (its system prompt + read/plan tools) for PLAN and the
> **engineer** agent (its system prompt + edit/bash tools + any granted skills mounted into the
> workspace + any granted MCP servers in `.mcp.json`) for IMPLEMENT — reflected in the claude
> invocation — with tools/skills/MCP outside the grant simply absent. Runs with no real agent
> (FakeAgentRuntime) and the existing 150 tests stay green.

## 2. Scope

### In scope
- **Pure capability domain** (`domain/capabilities.py`): stage→role mapping, agent selection with
  fallback, and a pure `AgentManifest` assembled from a selected agent + resolved registry rows.
- **`RunContext.agent`**: optional manifest the activity populates; the runtime composes from it.
- **`run_stage` activity**: loads the team's agents, selects per stage, resolves grant ids to
  registry rows, assembles the manifest, sets `ctx.agent`. Workflow input carries `team_id`.
- **`ClaudeCodeRuntime` composition**: `--append-system-prompt`, agent `allowed_tools`, **skills
  cloned/mounted** into `<workspace>/.claude/skills/`, and **`.mcp.json`** written + `--mcp-config`.
- **`SkillFetcher`** adapter (git clone for URLs, copy for paths; injectable).

### Out of scope (→ C3 / later)
- Secret **values + encryption + injection** (cred-needing MCP/skills are configured but
  unauthenticated until C3).
- Capability/tool **audit log** + active PreToolUse interceptor (C3).
- Per-stage **model alias** routing / LiteLLM (the agent's `model_alias` is recorded; routing is C3).
- Parallel engineers / multiple agents per stage (phase B).

## 3. Decisions log

| Decision | Choice | Rationale |
|---|---|---|
| Skills | **Clone + mount now** into `<workspace>/.claude/skills/<name>/` | The user wants real granted skills; claude discovers them there |
| Compose source | **Agent is source of truth** for system_prompt + allowed_tools; `prompts.for_stage` = task text; fallback to stage defaults if the agent grants no tools | Deny-by-default from grants; keep runs working when grants are sparse |
| Stage→role | **PLAN→lead, IMPLEMENT→backend, VERIFY→qa, LEARN→lead** | Matches the default team; pure + overridable later |
| Selection fallback | role → lead → first agent → None | A run never stalls because a role is missing |
| Manifest assembly | **per-stage, in the `run_stage` activity** (DB I/O), pure `assemble()` given resolved rows | Per-stage agent differs; keep domain pure, I/O in the activity |
| Composition site | **inside `ClaudeCodeRuntime.run_stage`** (it owns "set up claude then spawn") | Cohesive adapter; testable via fake spawn + fake fetcher |
| Skill fetch failure | **record an error event + skip that skill** (run continues) | A bad skill source shouldn't kill the run |

## 4. Architecture

```
src/
  domain/
    capabilities.py        # PURE: role_for_stage, select_agent, AgentManifest, assemble()
    runtime.py             # RunContext gains optional `agent: AgentManifest | None`
  adapters/
    skills/
      __init__.py
      fetcher.py           # SkillFetcher: clone (git URL) / copy (path) a skill source into a dest
      fake.py              # FakeSkillFetcher (records fetches) for tests
    runtime/claude_code.py # composes from ctx.agent: system prompt, tools, skills mount, .mcp.json
  interactors/temporal/
    activities.py          # run_stage: load team agents, select, resolve grants, assemble manifest
    workflows.py           # run_stage payload gains team_id (from inp)
    worker.py              # wire SkillFetcher into ClaudeCodeRuntime
  interactors/api/routes/runs.py  # start_run adds team_id to the workflow input (run already has it)
```

### Domain (pure) — key signatures
```python
# domain/capabilities.py
class SkillRef(BaseModel):
    name: str
    source: str

class McpRef(BaseModel):
    name: str
    transport: str
    command_or_url: str
    tool_allowlist: list[str] = []

class AgentManifest(BaseModel):
    system_prompt: str = ""
    allowed_tools: list[str] = []
    skills: list[SkillRef] = []
    mcp_servers: list[McpRef] = []

def role_for_stage(stage: RunStage) -> AgentRole | None: ...   # None for provision/pr
def select_agent(agents: list[AgentDefinition], stage: RunStage) -> AgentDefinition | None: ...
def assemble(agent: AgentDefinition, skills: list[Skill], mcp_servers: list[McpServer]) -> AgentManifest: ...
```

### `run_stage` activity (additions)
- payload gains `team_id`. Load `uow.agents.list(filters={"team_id": team_id})`; `select_agent(stage)`.
- If an agent is selected: resolve its `skill_ids`/`mcp_server_ids` via owner-scoped
  `uow.skills.get`/`uow.mcp_servers.get` (a missing grant → an error event, skipped — not fatal,
  since C1 validated them at create but a registry row could be deleted later), then
  `assemble(agent, skills, mcp_servers)` → `ctx.agent`.
- Pass `ctx` to `self._runtime.run_stage(ctx)` as today.

### `ClaudeCodeRuntime.run_stage` (when `ctx.agent`)
1. `task_prompt, default_tools = prompts.for_stage(...)`.
2. `tools = ctx.agent.allowed_tools or default_tools` + each mcp server's `tool_allowlist`.
3. For each `ctx.agent.skills`: `self._skills.fetch(skill.source, f"{ctx.workspace_path}/.claude/skills/{skill.name}")`; on failure, yield an error `AgentEvent` and continue.
4. If `ctx.agent.mcp_servers`: write `<workspace>/.mcp.json` (`{"mcpServers": {name: {...}}}`); add `--mcp-config .mcp.json`.
5. argv adds `--append-system-prompt <agent.system_prompt>` (when non-empty) and the composed `--allowedTools`.
6. Spawn + stream as today. When `ctx.agent` is None (fake/no-agent), behave exactly as A5ab.

### SkillFetcher
```python
# adapters/skills/fetcher.py
class SkillFetcher:
    def fetch(self, source: str, dest: str) -> None: ...   # git clone if URL-ish, else copytree
```
Injectable into `ClaudeCodeRuntime` (worker wires the real one; tests use `FakeSkillFetcher`).

## 5. Error handling
- Missing/deleted grant registry row at assembly → error `run_event`, skip that grant (don't fail).
- Skill fetch failure → error `run_event`, skip that skill; the stage still runs.
- `.mcp.json` write/`--mcp-config` only when there are granted servers; servers needing secrets are
  configured but unauthenticated until C3 (documented; not an error in C2).
- No agent selectable (empty team) → run with the A5ab default behavior (task prompt + stage tools).

## 6. Testing (80% gate)
- **Pure unit:** `role_for_stage` (incl. None for provision/pr), `select_agent` (role hit + fallbacks
  + empty), `assemble` (grants → manifest).
- **Runtime:** fake `spawn` + `FakeSkillFetcher`: asserts `--append-system-prompt`, agent
  `allowed_tools` in argv, `.mcp.json` written with granted servers, skills fetched to
  `.claude/skills/<name>`; skill-fetch failure path emits an event + continues; `ctx.agent=None`
  reproduces A5ab argv.
- **Activity:** seeded team+agent+skill+mcp → `run_stage` sets `ctx.agent` (assert via a spy runtime
  capturing the ctx); deleted-grant path skips gracefully.
- **Workflow:** `inp`/payload carries `team_id` end to end (FakeAgentRuntime ignores `ctx.agent`).
- Existing 150 tests stay green (fake path unchanged; `RunContext.agent` defaults None).

## 7. Risks
- **`.claude/skills` discovery** depends on claude-code's skill-loading conventions; pin the
  approach to the installed claude-code version, covered by the opt-in real test.
- **Skill clone cost/network** — mitigated by skip-on-failure + (future) caching; real fetch only in
  the opt-in test.
- **`team_id` threading** — the run row already has `team_id`; `start_run` must add it to the
  workflow input and the workflow must forward it to `run_stage` (covered by the workflow test).
