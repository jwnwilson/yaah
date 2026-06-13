# A5c-2 — Runtime composes per-stage agent grants — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Select the right agent per pipeline stage and have ClaudeCodeRuntime compose the claude invocation from that agent's grants (system prompt, allowed tools, mounted skills, MCP config).

**Architecture:** Pure `domain/capabilities.py` (stage→role, agent selection, `AgentManifest` + `assemble`); `RunContext` gains an optional `agent` manifest the `run_stage` activity populates (loading the team's agents + resolving grants); `ClaudeCodeRuntime` composes from it (`--append-system-prompt`, agent tools, skills cloned into `.claude/skills/`, `.mcp.json`); a `SkillFetcher` adapter does the cloning. `FakeAgentRuntime` ignores the manifest so existing tests stay green.

**Tech Stack:** Python 3.12 · Temporal · subprocess `git`/`claude` · pytest.

**Spec:** `docs/specs/2026-06-13-a5c2-runtime-capability-composition-design.md`

**Precondition:** A1–A5c-1 merged to `main`. Mirror: `domain/runtime.py` (RunContext/AgentEvent), `adapters/runtime/claude_code.py`, `interactors/temporal/activities.py` (`run_stage`), `interactors/temporal/workflows.py` (run_stage payload), `interactors/api/routes/runs.py` (`start_run` builds the workflow input), `domain/models.py` (AgentDefinition/Skill/McpServer/AgentRole/RunStage).

## Conventions
- TDD; `uv run pytest <path> -v`; `rm -rf ui/dist` before the full suite; commit per task with the given message.
- The agent/grant loading is **I/O → in the activity**, never the workflow body. The pure `assemble()` takes already-resolved rows.

## Parallel waves
- **Wave 1 (parallel, disjoint):** Lane DOMAIN = T1 (capabilities) → T2 (RunContext.agent) ‖ Lane SKILLS = T3 (SkillFetcher).
- **Wave 2 (parallel, disjoint):** Lane RUNTIME = T4 (ClaudeCodeRuntime compose + worker wiring) ‖ Lane PIPELINE = T5 (activity) → T6 (workflow + start_run team_id).
- **Wave 3:** T7 verify + integration PR.

---

## Task T1: Pure capability domain  (Lane DOMAIN)

**Files:** Create `src/domain/capabilities.py`; Test `tests/unit/test_capabilities.py`.

- [ ] **Step 1: failing test**
```python
# tests/unit/test_capabilities.py
from domain import capabilities as cap
from domain.models import AgentDefinition, AgentRole, McpServer, RunStage, Skill


def _agent(role, **kw):
    return AgentDefinition(team_id="t", role=role, name=role, model_alias="m", **kw)


def test_role_for_stage():
    assert cap.role_for_stage(RunStage.PLAN) == AgentRole.LEAD
    assert cap.role_for_stage(RunStage.IMPLEMENT) == AgentRole.BACKEND
    assert cap.role_for_stage(RunStage.VERIFY) == AgentRole.QA
    assert cap.role_for_stage(RunStage.PR) is None  # non-agent stage


def test_select_agent_by_role_then_fallback():
    lead, eng = _agent(AgentRole.LEAD), _agent(AgentRole.BACKEND)
    assert cap.select_agent([lead, eng], RunStage.IMPLEMENT) is eng
    assert cap.select_agent([lead], RunStage.VERIFY) is lead       # fallback -> lead
    assert cap.select_agent([eng], RunStage.PLAN) is eng           # fallback -> first
    assert cap.select_agent([], RunStage.PLAN) is None


def test_assemble_manifest_from_grants():
    agent = _agent(AgentRole.BACKEND, system_prompt="you build",
                   allowed_tools=["Read", "Edit"], skill_ids=["s1"], mcp_server_ids=["m1"])
    skills = [Skill(owner_id="u", name="pytest", source="git@x/s.git")]
    mcps = [McpServer(owner_id="u", name="fs", transport="stdio",
                      command_or_url="npx mcp-fs", tool_allowlist=["mcp__fs__read"])]
    man = cap.assemble(agent, skills, mcps)
    assert man.system_prompt == "you build" and man.allowed_tools == ["Read", "Edit"]
    assert man.skills[0].name == "pytest" and man.skills[0].source == "git@x/s.git"
    assert man.mcp_servers[0].tool_allowlist == ["mcp__fs__read"]
```

- [ ] **Step 2: red** → `uv run pytest tests/unit/test_capabilities.py -v` (ModuleNotFound).

- [ ] **Step 3: implement** `src/domain/capabilities.py`:
```python
"""Pure agent-capability policy: stage->role, agent selection, manifest assembly. No I/O."""

from pydantic import BaseModel

from domain.models import AgentDefinition, AgentRole, McpServer, RunStage, Skill

_STAGE_ROLE: dict[RunStage, AgentRole] = {
    RunStage.PLAN: AgentRole.LEAD,
    RunStage.IMPLEMENT: AgentRole.BACKEND,
    RunStage.VERIFY: AgentRole.QA,
    RunStage.LEARN: AgentRole.LEAD,
}


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


def role_for_stage(stage: RunStage) -> AgentRole | None:
    return _STAGE_ROLE.get(stage)


def select_agent(agents: list[AgentDefinition], stage: RunStage) -> AgentDefinition | None:
    if not agents:
        return None
    role = role_for_stage(stage)
    by_role = {a.role: a for a in agents}
    if role is not None and role in by_role:
        return by_role[role]
    if AgentRole.LEAD in by_role:
        return by_role[AgentRole.LEAD]
    return agents[0]


def assemble(agent: AgentDefinition, skills: list[Skill],
             mcp_servers: list[McpServer]) -> AgentManifest:
    return AgentManifest(
        system_prompt=agent.system_prompt,
        allowed_tools=list(agent.allowed_tools),
        skills=[SkillRef(name=s.name, source=s.source) for s in skills],
        mcp_servers=[McpRef(name=m.name, transport=m.transport,
                            command_or_url=m.command_or_url,
                            tool_allowlist=list(m.tool_allowlist)) for m in mcp_servers],
    )
```

- [ ] **Step 4: green** → PASS.
- [ ] **Step 5: commit**
```bash
git add src/domain/capabilities.py tests/unit/test_capabilities.py
git commit -m "feat: pure agent-capability policy (role/selection/manifest)"
```

---

## Task T2: RunContext gains optional agent manifest  (Lane DOMAIN)

**Files:** Modify `src/domain/runtime.py`; Test `tests/unit/test_runtime_dtos.py`.

- [ ] **Step 1: failing test** — add:
```python
def test_run_context_carries_optional_agent_manifest():
    from domain.capabilities import AgentManifest
    from domain.models import RunStage
    from domain.runtime import RunContext

    ctx = RunContext(run_id="r", stage=RunStage.IMPLEMENT, task_title="t",
                     workspace_path="/ws",
                     agent=AgentManifest(system_prompt="sp", allowed_tools=["Read"]))
    assert ctx.agent is not None and ctx.agent.system_prompt == "sp"

    bare = RunContext(run_id="r", stage=RunStage.PLAN, task_title="t", workspace_path="/ws")
    assert bare.agent is None
```

- [ ] **Step 2: red** → TypeError (no `agent` field).

- [ ] **Step 3: implement** — in `src/domain/runtime.py` add the import and field:
```python
from domain.capabilities import AgentManifest   # add near the top imports
```
and add to `RunContext` (after `prior_artifacts`):
```python
    agent: AgentManifest | None = None
```

- [ ] **Step 4: green** → PASS (existing runtime DTO tests still pass — field defaults None).
- [ ] **Step 5: commit**
```bash
git add src/domain/runtime.py tests/unit/test_runtime_dtos.py
git commit -m "feat: RunContext carries optional AgentManifest"
```

---

## Task T3: SkillFetcher adapter + fake  (Lane SKILLS)

**Files:** Create `src/adapters/skills/__init__.py`, `fetcher.py`, `fake.py`; Test `tests/unit/test_skill_fetcher.py`.

- [ ] **Step 1: failing test**
```python
# tests/unit/test_skill_fetcher.py
import os
import tempfile

from adapters.skills.fake import FakeSkillFetcher
from adapters.skills.fetcher import SkillFetcher


def test_fake_records_fetches():
    f = FakeSkillFetcher()
    f.fetch("git@x/s.git", "/ws/.claude/skills/pytest")
    assert f.fetched == [("git@x/s.git", "/ws/.claude/skills/pytest")]


def test_local_path_source_is_copied():
    src = tempfile.mkdtemp()
    open(os.path.join(src, "SKILL.md"), "w").write("# skill")
    dest = os.path.join(tempfile.mkdtemp(), "pytest")
    SkillFetcher().fetch(src, dest)
    assert os.path.exists(os.path.join(dest, "SKILL.md"))
```

- [ ] **Step 2: red** → ModuleNotFound.

- [ ] **Step 3: implement**

`src/adapters/skills/__init__.py` (empty). `src/adapters/skills/fetcher.py`:
```python
import shutil
import subprocess
from pathlib import Path


def _is_git_source(source: str) -> bool:
    return source.endswith(".git") or source.startswith(("git@", "http://", "https://", "ssh://"))


class SkillFetcher:
    """Fetch a granted skill's source into `dest`. Git URL -> clone; local path -> copy."""

    def fetch(self, source: str, dest: str) -> None:
        dest_path = Path(dest)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        if _is_git_source(source):
            proc = subprocess.run(["git", "clone", "--depth", "1", source, dest],
                                  capture_output=True, text=True)
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr.strip() or "skill clone failed")
        else:
            if dest_path.exists():
                shutil.rmtree(dest_path)
            shutil.copytree(source, dest)
```

`src/adapters/skills/fake.py`:
```python
class FakeSkillFetcher:
    """Records fetches; no filesystem/network. `fail_on` triggers a RuntimeError for a source."""

    def __init__(self, fail_on: str | None = None):
        self.fetched: list[tuple[str, str]] = []
        self._fail_on = fail_on

    def fetch(self, source: str, dest: str) -> None:
        if self._fail_on is not None and source == self._fail_on:
            raise RuntimeError(f"cannot fetch {source}")
        self.fetched.append((source, dest))
```

- [ ] **Step 4: green** → PASS.
- [ ] **Step 5: commit**
```bash
git add src/adapters/skills tests/unit/test_skill_fetcher.py
git commit -m "feat: SkillFetcher (git clone / copy) + FakeSkillFetcher"
```

---

## Task T4: ClaudeCodeRuntime composes from the manifest  (Lane RUNTIME, wave 2)

**Files:** Modify `src/adapters/runtime/claude_code.py`, `src/interactors/temporal/worker.py`; Test `tests/unit/test_claude_code_runtime.py`.

> Needs T1/T2 (manifest, ctx.agent) + T3 (fetcher).

- [ ] **Step 1: failing test** — add to `tests/unit/test_claude_code_runtime.py`:
```python
import json
import os
import tempfile

from adapters.model.fake import FakeModelProvider
from adapters.skills.fake import FakeSkillFetcher
from adapters.runtime.claude_code import ClaudeCodeRuntime
from domain.capabilities import AgentManifest, McpRef, SkillRef
from domain.models import RunStage
from domain.runtime import RunContext


class _FakeProc:
    def __init__(self, lines):
        self.stdout = iter(lines); self.stderr = iter([]); self.pid = 1; self.returncode = 0
    def wait(self): return 0


def _result_line():
    return json.dumps({"type": "result", "is_error": False, "total_cost_usd": 0.1})


def test_composes_system_prompt_tools_skills_and_mcp():
    ws = tempfile.mkdtemp()
    man = AgentManifest(system_prompt="you are eng", allowed_tools=["Read", "Edit"],
                        skills=[SkillRef(name="pytest", source="git@x/s.git")],
                        mcp_servers=[McpRef(name="fs", transport="stdio",
                                            command_or_url="npx mcp-fs",
                                            tool_allowlist=["mcp__fs__read"])])
    ctx = RunContext(run_id="r1", stage=RunStage.IMPLEMENT, task_title="T",
                     acceptance_criteria=[], workspace_path=ws, agent=man)
    captured = {}
    def spawn(argv, **kw):
        captured["argv"] = argv
        return _FakeProc([_result_line()])
    fetcher = FakeSkillFetcher()
    rt = ClaudeCodeRuntime(FakeModelProvider(), spawn=spawn, skills=fetcher)
    list(rt.run_stage(ctx))
    argv = captured["argv"]
    assert "--append-system-prompt" in argv and "you are eng" in argv
    assert "Read" in argv and "Edit" in argv and "mcp__fs__read" in argv
    assert "--mcp-config" in argv
    assert fetcher.fetched and fetcher.fetched[0][0] == "git@x/s.git"
    assert os.path.exists(os.path.join(ws, ".mcp.json"))


def test_skill_fetch_failure_is_skipped_not_fatal():
    ws = tempfile.mkdtemp()
    man = AgentManifest(skills=[SkillRef(name="bad", source="git@x/bad.git")])
    ctx = RunContext(run_id="r1", stage=RunStage.IMPLEMENT, task_title="T",
                     workspace_path=ws, agent=man)
    rt = ClaudeCodeRuntime(FakeModelProvider(), spawn=lambda a, **k: _FakeProc([_result_line()]),
                           skills=FakeSkillFetcher(fail_on="git@x/bad.git"))
    events = list(rt.run_stage(ctx))
    from adapters.runtime.fake import result_of
    assert result_of(events).outcome == "ok"  # run continued despite the bad skill
```

- [ ] **Step 2: red** → `ClaudeCodeRuntime` has no `skills` param / no composition.

- [ ] **Step 3: implement** — update `src/adapters/runtime/claude_code.py`:
  - constructor: `def __init__(self, model, *, spawn=subprocess.Popen, skills=None):` store `self._skills = skills or SkillFetcher()` (import `from adapters.skills.fetcher import SkillFetcher`).
  - in `run_stage`, after building `task_prompt, default_tools = prompts.for_stage(...)`:
```python
        argv = ["claude", "-p", task_prompt, "--output-format", "stream-json", "--verbose"]
        tools = list(default_tools)
        if ctx.agent is not None:
            if ctx.agent.system_prompt:
                argv += ["--append-system-prompt", ctx.agent.system_prompt]
            tools = list(ctx.agent.allowed_tools) or list(default_tools)
            for mcp in ctx.agent.mcp_servers:
                tools += mcp.tool_allowlist
            for skill in ctx.agent.skills:
                try:
                    self._skills.fetch(skill.source,
                                       os.path.join(ctx.workspace_path, ".claude", "skills", skill.name))
                except Exception as exc:  # noqa: BLE001 - skip a bad skill, don't fail the stage
                    events_pre.append(AgentEvent(type="progress", stage=ctx.stage,
                                                 message=f"skill '{skill.name}' skipped: {exc}"))
            if ctx.agent.mcp_servers:
                _write_mcp_config(ctx.workspace_path, ctx.agent.mcp_servers)
                argv += ["--mcp-config", os.path.join(ctx.workspace_path, ".mcp.json")]
        argv += ["--allowedTools", *tools,
                 "--max-turns", str(prompts.max_turns(ctx.stage)),
                 "--model", self._model.model_id()]
```
  Initialise `events_pre: list[AgentEvent] = []` before this block, spawn as today, and `yield from events_pre` before yielding the streamed events. Add the helper at module scope:
```python
def _write_mcp_config(workspace_path: str, servers) -> None:
    import json
    cfg = {"mcpServers": {s.name: {"command": s.command_or_url} if s.transport == "stdio"
                          else {"url": s.command_or_url} for s in servers}}
    with open(os.path.join(workspace_path, ".mcp.json"), "w") as f:
        json.dump(cfg, f)
```
  (Keep the existing `--allowedTools`/`--max-turns`/`--model` only once — the block above replaces the old argv assembly. Ensure `import os` is present.)

  Update `worker.py` `_build_runtime`: `ClaudeCodeRuntime(_build_model_provider(settings))` → `ClaudeCodeRuntime(_build_model_provider(settings), skills=SkillFetcher())` (import `from adapters.skills.fetcher import SkillFetcher`).

- [ ] **Step 4: green** → `uv run pytest tests/unit/test_claude_code_runtime.py -v` (incl. the A5ab tests where `ctx.agent` is None → original argv path) ; `uv run ruff check src tests`.
- [ ] **Step 5: commit**
```bash
git add src/adapters/runtime/claude_code.py src/interactors/temporal/worker.py tests/unit/test_claude_code_runtime.py
git commit -m "feat: ClaudeCodeRuntime composes from the agent manifest"
```

---

## Task T5: run_stage activity assembles the manifest  (Lane PIPELINE, wave 2)

**Files:** Modify `src/interactors/temporal/activities.py`; Test `tests/unit/test_activities.py`.

> Needs T1/T2. Independent of the RUNTIME lane (different files).

- [ ] **Step 1: failing test** — a spy runtime captures the ctx; seed team+agent+skill+mcp:
```python
def test_run_stage_populates_ctx_agent_from_team():
    factory = _factory()
    run_id = _seed_run(factory)  # existing helper; run has team_id "tm1"? -> see note
    # seed a team agent + a granted skill in the same owner scope
    from adapters.database.uow import SqlUnitOfWork
    from domain.models import AgentDefinition, McpServer, Skill, Team
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        team = uow.teams.create(Team(owner_id="u1", name="T"))
        sk = uow.skills.create(Skill(owner_id="u1", name="pytest", source="git@x/s.git"))
        uow.agents.create(AgentDefinition(team_id=team.id, role="backend", name="Eng",
                                          model_alias="m", system_prompt="build",
                                          allowed_tools=["Read", "Edit"], skill_ids=[sk.id]))

    captured = {}
    class _Spy:
        def run_stage(self, ctx):
            captured["ctx"] = ctx
            from domain.runtime import AgentEvent, StageResult
            yield AgentEvent(type="result", stage=ctx.stage, message="ok",
                             data=StageResult(outcome="ok").model_dump())
        def cancel(self, run_id): ...

    from adapters.storage.local import LocalStorageAdapter
    import tempfile
    from interactors.temporal.activities import RunActivities
    from adapters.git.fake import FakeGit
    from adapters.forge.fake import FakeGitForge
    acts = RunActivities(factory, _Spy(), LocalStorageAdapter(base_dir=tempfile.mkdtemp()),
                         FakeGit(), FakeGitForge())
    acts.run_stage({"run_id": run_id, "owner_id": "u1", "stage": "implement",
                    "task_title": "T", "acceptance_criteria": [], "team_id": team.id})
    ctx = captured["ctx"]
    assert ctx.agent is not None
    assert ctx.agent.system_prompt == "build" and ctx.agent.allowed_tools == ["Read", "Edit"]
    assert ctx.agent.skills[0].source == "git@x/s.git"
```
> If `_seed_run`/`_factory`/`RunActivities` builder differ in the file, adapt to the existing helpers — the assertions stand.

- [ ] **Step 2: red** → `ctx.agent` is None (activity doesn't assemble it).

- [ ] **Step 3: implement** — in `run_stage` (activities.py), after computing `workspace_path` and before building `RunContext`, assemble the manifest when `team_id` is present:
```python
        agent_manifest = None
        team_id = payload.get("team_id")
        if team_id:
            from domain import capabilities
            uow = self._uow(payload["owner_id"])
            with uow.transaction():
                agents = uow.agents.list(filters={"team_id": team_id}, page_size=100).results
                selected = capabilities.select_agent(agents, RunStage(payload["stage"]))
                if selected is not None:
                    skills, mcps = [], []
                    for sid in selected.skill_ids:
                        try:
                            skills.append(uow.skills.get(sid))
                        except Exception:  # noqa: BLE001 - deleted grant: skip, don't fail
                            pass
                    for mid in selected.mcp_server_ids:
                        try:
                            mcps.append(uow.mcp_servers.get(mid))
                        except Exception:  # noqa: BLE001
                            pass
                    agent_manifest = capabilities.assemble(selected, skills, mcps)
```
and pass `agent=agent_manifest` into the `RunContext(...)` constructor.

- [ ] **Step 4: green** → `uv run pytest tests/unit/test_activities.py -v` PASS (existing run_stage tests still pass — no `team_id` → `agent` stays None).
- [ ] **Step 5: commit**
```bash
git add src/interactors/temporal/activities.py tests/unit/test_activities.py
git commit -m "feat: run_stage assembles the per-stage agent manifest"
```

---

## Task T6: Thread team_id through workflow + start_run  (Lane PIPELINE, wave 2)

**Files:** Modify `src/interactors/temporal/workflows.py`, `src/interactors/api/routes/runs.py`; Test `tests/workflow/test_run_workflow.py`, `tests/integration/test_runs_api.py`.

- [ ] **Step 1: failing test** — workflow forwards team_id into the run_stage payload. Add to `tests/integration/test_runs_api.py`:
```python
def test_start_run_passes_team_id():
    c, fake = _client_with_fake_temporal()
    task_id, _t, _p = _ready_task(c)
    c.post(f"/work-items/{task_id}/runs")
    assert "team_id" in fake.started[0] and fake.started[0]["team_id"]
```

- [ ] **Step 2: red** → `team_id` not in the workflow input.

- [ ] **Step 3: implement**
  - `runs.py` `start_run`: the `run` already has `team_id`; add to `run_input`:
    ```python
            "team_id": run.team_id,
    ```
  - `workflows.py`: in the `run_stage` activity payload (the `else` branch dispatching `"run_stage"`), add:
    ```python
                        "team_id": inp.get("team_id"),
    ```

- [ ] **Step 4: green** → `uv run pytest tests/integration/test_runs_api.py tests/workflow/ -v` PASS (workflow tests pass `team_id` optional; FakeAgentRuntime ignores `ctx.agent`).
- [ ] **Step 5: commit**
```bash
git add src/interactors/temporal/workflows.py src/interactors/api/routes/runs.py tests/integration/test_runs_api.py tests/workflow/test_run_workflow.py
git commit -m "feat: thread team_id into run_stage so the agent is selected"
```

---

## Task T7: Full verify + integration PR  (Wave 3)

- [ ] **Step 1:** `rm -rf ui/dist && uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=80` → all pass, ≥80%.
- [ ] **Step 2:** `uv run ruff check src tests` → clean.
- [ ] **Step 3:** Commit fixes; open the integration PR to `main`.

> Coverage note: `SkillFetcher.fetch` git-clone branch + `_write_mcp_config` http branch may use `# pragma: no cover` where they need a real clone — never `capabilities`, `assemble`, `select_agent`, the activity assembly, or the runtime compose path (all covered offline).

---

## Self-review (resolved)

- **Spec §4 domain** ↔ T1 (capabilities: role/select/assemble + manifest DTOs), T2 (RunContext.agent). ✅
- **Spec §4 activity/runtime/skills** ↔ T5 (activity assembles), T4 (runtime composes + worker wiring), T3 (SkillFetcher). ✅
- **Spec §4 team_id threading** ↔ T6 (start_run + workflow). ✅
- **Spec §5 error handling** ↔ skill-fetch failure skipped (T4), deleted-grant skipped (T5), `.mcp.json` only when servers exist (T4), no-agent → A5ab path (T4). ✅
- **Spec §6 testing** ↔ pure (T1), runtime compose + skip (T4), activity assembly (T5), team_id end-to-end (T6); fake path unchanged. ✅
- **Type consistency:** `AgentManifest`/`SkillRef`/`McpRef` defined in `domain/capabilities.py` (T1), imported by `RunContext` (T2), built by `assemble` (T1) + activity (T5), consumed by runtime (T4). `select_agent(agents, stage)` + `role_for_stage(stage)` signatures match across T1/T5. `ClaudeCodeRuntime(model, *, spawn, skills)` consistent T4 + worker. payload key `team_id` consistent T5/T6. ✅
- **No change to FakeAgentRuntime / pipeline stages** — `ctx.agent` defaults None; PROVISION/PR untouched. ✅
```
