# Extract Claude Invocation Policy into the Domain — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the pure Claude-Code invocation policy out of `adapters/runtime/claude_code.py` into a new pure domain module so it is unit-testable without `subprocess`, leaving the adapter as thin orchestration.

**Architecture:** Add `domain/agent_invocation.py` with an `AgentInvocation` Pydantic DTO and a pure `build_invocation(ctx, *, model_id)` function that produces the full `argv`, the extra env vars, the config files to write, and the skills to fetch. The adapter then resolves the model id, calls `build_invocation`, fetches skills, writes files, merges env, and spawns the process. Observable behavior (argv/env/files) is unchanged — the existing adapter test file is the regression contract and must stay green with **zero edits**.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, `uv`. Hexagonal layering (`domain/` is pure, no I/O).

**Spec:** `docs/superpowers/specs/2026-06-14-adapter-invocation-policy-extraction-design.md`

---

## File Structure

- **Create** `src/domain/agent_invocation.py` — `AgentInvocation` DTO + pure `build_invocation`. One responsibility: turn a `RunContext` + resolved `model_id` into everything needed to launch the agent. No I/O.
- **Create** `tests/unit/test_agent_invocation.py` — pure unit tests for `build_invocation`.
- **Modify** `src/adapters/runtime/claude_code.py` — delete `_write_agent_settings` / `_write_mcp_config` and the inline policy in `run_stage`; delegate to `build_invocation`; keep spawn/parse/cancel.
- **Unchanged** `tests/unit/test_claude_code_runtime.py` — the adapter behavior contract. Do not edit. It must pass after Task 3.

---

## Task 1: Pure `build_invocation` — no-agent path

**Files:**
- Create: `src/domain/agent_invocation.py`
- Test: `tests/unit/test_agent_invocation.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_agent_invocation.py`:

```python
from domain.agent_invocation import AgentInvocation, build_invocation
from domain.models import RunStage
from domain.runtime import RunContext


def _ctx(stage=RunStage.IMPLEMENT, **kw):
    base = dict(run_id="r1", stage=stage, task_title="Add login",
                acceptance_criteria=["works"], workspace_path="/ws")
    base.update(kw)
    return RunContext(**base)


def test_no_agent_argv_has_core_flags_and_no_extras():
    inv = build_invocation(_ctx(), model_id="sonnet")

    assert isinstance(inv, AgentInvocation)
    assert inv.argv[0] == "claude"
    assert "-p" in inv.argv
    assert "--output-format" in inv.argv and "stream-json" in inv.argv
    assert "--verbose" in inv.argv
    assert inv.argv.count("--allowedTools") == 1
    assert inv.argv.count("--max-turns") == 1
    i = inv.argv.index("--model")
    assert inv.argv[i + 1] == "sonnet"
    # no agent -> no settings/mcp files, no extra env, no skills, no mcp flag
    assert inv.files == {}
    assert inv.env_extra == {}
    assert inv.skills == []
    assert inv.mcp_config_path is None
    assert "--append-system-prompt" not in inv.argv
    assert "--mcp-config" not in inv.argv
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_agent_invocation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'domain.agent_invocation'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/domain/agent_invocation.py`:

```python
"""Pure policy that builds the Claude Code CLI invocation for a run stage. No I/O."""

import json
import os

from pydantic import BaseModel

from domain import prompts
from domain.runtime import RunContext

_SETTINGS = {
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "*",
                "hooks": [
                    {"type": "command", "command": "python -m adapters.runtime.pretooluse_hook"}
                ],
            }
        ]
    }
}


class AgentInvocation(BaseModel):
    argv: list[str]
    env_extra: dict[str, str] = {}
    files: dict[str, str] = {}            # relpath -> JSON content
    skills: list[tuple[str, str, str]] = []  # (name, source, dest)
    mcp_config_path: str | None = None


def _mcp_config(servers, secret_env) -> dict:
    env = secret_env or {}
    mcp: dict = {}
    for s in servers:
        entry = (
            {"command": s.command_or_url}
            if s.transport == "stdio"
            else {"url": s.command_or_url}
        )
        if env:
            entry["env"] = dict(env)
        mcp[s.name] = entry
    return {"mcpServers": mcp}


def build_invocation(ctx: RunContext, *, model_id: str) -> AgentInvocation:
    body = ctx.prior_artifacts.get("body", "") if ctx.prior_artifacts else ""
    task_prompt, default_tools = prompts.for_stage(
        ctx.stage, ctx.task_title, ctx.acceptance_criteria, body
    )
    argv = ["claude", "-p", task_prompt, "--output-format", "stream-json", "--verbose"]
    tools = list(default_tools)
    files: dict[str, str] = {}
    env_extra: dict[str, str] = {}
    skills: list[tuple[str, str, str]] = []
    mcp_config_path: str | None = None

    agent = ctx.agent
    if agent is not None:
        if agent.system_prompt:
            argv += ["--append-system-prompt", agent.system_prompt]
        tools = list(agent.allowed_tools) if agent.allowed_tools else list(default_tools)
        for mcp in agent.mcp_servers:
            tools += mcp.tool_allowlist
        for skill in agent.skills:
            dest = os.path.join(ctx.workspace_path, ".claude", "skills", skill.name)
            skills.append((skill.name, skill.source, dest))
        if agent.mcp_servers:
            files[".mcp.json"] = json.dumps(_mcp_config(agent.mcp_servers, agent.secret_env))
            mcp_config_path = os.path.join(ctx.workspace_path, ".mcp.json")
            argv += ["--mcp-config", mcp_config_path]

    argv += [
        "--allowedTools", *tools,
        "--max-turns", str(prompts.max_turns(ctx.stage)),
        "--model", model_id,
    ]

    if agent is not None:
        files[".claude/settings.json"] = json.dumps(_SETTINGS)
        env_extra = {
            **(agent.secret_env or {}),
            "YAAH_ALLOWED_TOOLS": json.dumps(tools),
            "YAAH_AUDIT_PATH": os.path.join(ctx.workspace_path, "audit.jsonl"),
            "YAAH_RUN_ID": ctx.run_id,
            "YAAH_STAGE": str(ctx.stage.value),
        }

    return AgentInvocation(
        argv=argv,
        env_extra=env_extra,
        files=files,
        skills=skills,
        mcp_config_path=mcp_config_path,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_agent_invocation.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/domain/agent_invocation.py tests/unit/test_agent_invocation.py
git commit -m "feat: pure build_invocation (no-agent path) for Claude runtime"
```

---

## Task 2: Pure `build_invocation` — agent path (tools, MCP, skills, settings, env)

**Files:**
- Test: `tests/unit/test_agent_invocation.py` (append tests)

The implementation from Task 1 already handles the agent path; this task pins that behavior with tests. Each test must pass against the existing module.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_agent_invocation.py`:

```python
import json

from domain.capabilities import AgentManifest, McpRef, SkillRef


def test_agent_tools_override_stage_defaults():
    man = AgentManifest(allowed_tools=["MyTool"])
    inv = build_invocation(_ctx(agent=man), model_id="sonnet")

    i = inv.argv.index("--allowedTools")
    rest = inv.argv[i + 1:]
    end = next((j for j, a in enumerate(rest) if a.startswith("--")), len(rest))
    assert rest[:end] == ["MyTool"]


def test_agent_empty_tools_fall_back_to_stage_defaults():
    from domain import prompts
    man = AgentManifest(allowed_tools=[])
    inv = build_invocation(_ctx(agent=man), model_id="sonnet")

    _, defaults = prompts.for_stage(RunStage.IMPLEMENT, "T", [], "")
    for t in defaults:
        assert t in inv.argv


def test_system_prompt_skills_and_mcp_compose():
    man = AgentManifest(
        system_prompt="you are eng",
        allowed_tools=["Read", "Edit"],
        skills=[SkillRef(name="pytest", source="git@x/s.git")],
        mcp_servers=[McpRef(name="fs", transport="stdio",
                            command_or_url="npx mcp-fs",
                            tool_allowlist=["mcp__fs__read"])],
    )
    inv = build_invocation(_ctx(agent=man, workspace_path="/ws"), model_id="sonnet")

    assert "--append-system-prompt" in inv.argv and "you are eng" in inv.argv
    assert "mcp__fs__read" in inv.argv          # mcp allowlist merged into tools
    assert "--mcp-config" in inv.argv
    assert inv.mcp_config_path == "/ws/.mcp.json"
    assert inv.skills == [("pytest", "git@x/s.git", "/ws/.claude/skills/pytest")]
    cfg = json.loads(inv.files[".mcp.json"])
    assert cfg["mcpServers"]["fs"]["command"] == "npx mcp-fs"


def test_no_mcp_means_no_mcp_file_or_flag():
    man = AgentManifest(system_prompt="sp")
    inv = build_invocation(_ctx(agent=man), model_id="sonnet")

    assert "--mcp-config" not in inv.argv
    assert ".mcp.json" not in inv.files
    assert inv.mcp_config_path is None


def test_secret_env_in_env_extra_and_mcp_file():
    man = AgentManifest(
        allowed_tools=["Read"],
        secret_env={"GH_TOKEN": "ghp_x"},
        mcp_servers=[McpRef(name="fs", transport="stdio", command_or_url="npx mcp-fs")],
    )
    inv = build_invocation(_ctx(agent=man, workspace_path="/ws"), model_id="sonnet")

    assert inv.env_extra["GH_TOKEN"] == "ghp_x"
    cfg = json.loads(inv.files[".mcp.json"])
    assert cfg["mcpServers"]["fs"]["env"]["GH_TOKEN"] == "ghp_x"


def test_yaah_env_block_set_when_agent_present():
    man = AgentManifest(allowed_tools=["Read", "Edit"])
    inv = build_invocation(_ctx(agent=man, run_id="r1", workspace_path="/ws"), model_id="sonnet")

    assert json.loads(inv.env_extra["YAAH_ALLOWED_TOOLS"]) == ["Read", "Edit"]
    assert inv.env_extra["YAAH_AUDIT_PATH"] == "/ws/audit.jsonl"
    assert inv.env_extra["YAAH_RUN_ID"] == "r1"
    assert inv.env_extra["YAAH_STAGE"] == "implement"
    assert "PreToolUse" in inv.files[".claude/settings.json"]
    assert "pretooluse_hook" in inv.files[".claude/settings.json"]


def test_model_id_is_used_verbatim():
    man = AgentManifest(allowed_tools=["Read"])
    inv = build_invocation(_ctx(agent=man), model_id="engineer-model")
    i = inv.argv.index("--model")
    assert inv.argv[i + 1] == "engineer-model"
```

- [ ] **Step 2: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_agent_invocation.py -v`
Expected: PASS (all tests, old and new). If any fails, the implementation drifted from the contract — fix `agent_invocation.py`, not the tests.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_agent_invocation.py
git commit -m "test: pin agent-path behavior of build_invocation"
```

---

## Task 3: Refactor the adapter to delegate to `build_invocation`

**Files:**
- Modify: `src/adapters/runtime/claude_code.py`

- [ ] **Step 1: Replace the file contents**

Overwrite `src/adapters/runtime/claude_code.py` with:

```python
import os
import signal
import subprocess
from typing import Iterator

from adapters.model.ports import ModelProvider
from adapters.runtime import stream_json
from adapters.skills.fetcher import SkillFetcher
from domain.agent_invocation import build_invocation
from domain.runtime import AgentEvent, RunContext, StageResult


class ClaudeCodeRuntime:
    """AgentRuntime backed by the Claude Code CLI as a subprocess in the workspace.
    `spawn` is injectable so tests never launch real claude."""

    def __init__(self, model: ModelProvider, *, spawn=subprocess.Popen, skills=None):
        self._model = model
        self._spawn = spawn
        self._skills = skills if skills is not None else SkillFetcher()
        self._procs: dict[str, object] = {}

    def run_stage(self, ctx: RunContext) -> Iterator[AgentEvent]:
        model_id = self._model.model_id()
        if ctx.agent is not None and ctx.agent.model_alias:
            model_id = ctx.agent.model_alias
        inv = build_invocation(ctx, model_id=model_id)

        events_pre: list[AgentEvent] = []
        for name, source, dest in inv.skills:
            try:
                self._skills.fetch(source, dest)
            except Exception as exc:  # noqa: BLE001 - skip a bad skill, don't fail the stage
                events_pre.append(AgentEvent(
                    type="progress",
                    stage=ctx.stage,
                    message=f"skill '{name}' skipped: {exc}",
                ))

        for relpath, content in inv.files.items():
            path = os.path.join(ctx.workspace_path, relpath)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(content)

        env = {**os.environ, **self._model.agent_env(), **inv.env_extra}
        proc = self._spawn(
            inv.argv, cwd=ctx.workspace_path, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True,
        )
        self._procs[ctx.run_id] = proc
        try:
            events, _result = stream_json.parse(proc.stdout, ctx.stage)
        finally:
            proc.wait()
            self._procs.pop(ctx.run_id, None)

        if not any(e.type == "result" for e in events):
            fail = StageResult(outcome="fail")
            events.append(AgentEvent(
                type="result", stage=ctx.stage,
                message="claude exited without a result", data=fail.model_dump(),
            ))

        yield from events_pre
        yield from events

    def cancel(self, run_id: str) -> None:  # pragma: no cover - needs a real process group
        proc = self._procs.get(run_id)
        if proc is not None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
```

- [ ] **Step 2: Run the unchanged adapter contract tests**

Run: `uv run pytest tests/unit/test_claude_code_runtime.py -v`
Expected: PASS — all tests, with **no edits** to that file. This proves argv/env/files behavior is preserved.

If a test fails, do not edit the test. Diff the expected vs actual argv/env/files and correct `agent_invocation.py` or the adapter so behavior matches the original.

- [ ] **Step 3: Commit**

```bash
git add src/adapters/runtime/claude_code.py
git commit -m "refactor: claude_code adapter delegates to domain build_invocation"
```

---

## Task 4: Full suite + coverage gate

**Files:** none (verification only)

- [ ] **Step 1: Run the full unit + integration suite**

Run: `uv run pytest -q`
Expected: PASS (no regressions across worker/activities/workflow tests that import the runtime).

- [ ] **Step 2: Run the coverage gate**

Run: `make coverage`
Expected: PASS — ≥ 80% gate holds; `domain/agent_invocation.py` is covered by `test_agent_invocation.py`.

- [ ] **Step 3: Commit (only if anything changed)**

```bash
git add -A
git commit -m "chore: verify coverage after invocation policy extraction" || echo "nothing to commit"
```

---

## Self-Review (completed by plan author)

- **Spec coverage:** new `domain/agent_invocation.py` (Tasks 1–2) ✓; adapter delegation (Task 3) ✓; new pure tests + unchanged adapter contract (Tasks 1–3) ✓; coverage gate (Task 4) ✓; non-goals untouched (no stream_json / `_TOOL` / DB / lib changes) ✓.
- **Placeholder scan:** none — every code step has complete code.
- **Type consistency:** `AgentInvocation` fields (`argv`, `env_extra`, `files`, `skills` as `(name, source, dest)` triples, `mcp_config_path`) and `build_invocation(ctx, *, model_id)` are used identically in the tests and the adapter.
