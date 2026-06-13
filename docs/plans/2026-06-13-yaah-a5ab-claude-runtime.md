# A5a+A5b — Claude Code runtime in a containerized worker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `FakeAgentRuntime` with a real `ClaudeCodeRuntime` (subprocess `claude`, streamed) selected automatically when a key+binary are present, with the worker running in a hardened Docker container.

**Architecture:** Pure `domain/prompts.py` (stage prompt + allowedTools) and pure `adapters/runtime/stream_json.py` (parse claude stream-json → events + StageResult incl. real cost); a `ModelProvider` port with a default `AnthropicProvider`; `ClaudeCodeRuntime` composes them with an injectable `spawn`; the worker auto-selects runtime; `infra/worker/Dockerfile` + a hardened compose `worker` service. `FakeAgentRuntime` stays the default so the existing 124 tests stay green.

**Tech Stack:** Python 3.12 · Temporal · subprocess `claude` (Claude Code CLI) · Docker/compose · pytest (pure + monkeypatched subprocess + opt-in real).

**Spec:** `docs/specs/2026-06-13-a5ab-claude-runtime-sandbox-design.md`

**Precondition:** A1–A4a merged to `main` (`AgentRuntime` port in `domain/runtime.py`; `RunActivities`; `worker.build_activities`; A4a git/forge/storage).

## Conventions
- TDD: failing test → red → minimal impl → green → commit. `uv run pytest <path> -v`.
- `rm -rf ui/dist` before the full suite.
- Activity/runtime code is sync; the `claude` subprocess is injectable (`spawn=`) so tests never launch real claude.

## Parallel waves
- **Wave 1 (parallel, disjoint):** Lane PROMPTS (T1) ‖ Lane PARSER (T2) ‖ Lane MODEL (T3–T4) ‖ Lane INFRA (T7).
- **Wave 2 (one lane):** Lane RUNTIME (T5 ClaudeCodeRuntime → T6 worker auto-select).
- **Wave 3:** T8 full verify + integration PR.

---

## Task T1: Pure stage prompts  (Lane PROMPTS)

**Files:** Create `src/domain/prompts.py`; Test `tests/unit/test_prompts.py`.

- [ ] **Step 1: failing test**
```python
# tests/unit/test_prompts.py
from domain import prompts
from domain.models import RunStage


def test_implement_prompt_has_edit_tools_and_criteria():
    text, tools = prompts.for_stage(RunStage.IMPLEMENT, "Add login", ["works", "tested"], "do it")
    assert "Add login" in text and "- works" in text
    assert "Edit" in tools and "Bash" in tools


def test_verify_is_read_only():
    _text, tools = prompts.for_stage(RunStage.VERIFY, "X", [], "")
    assert "Edit" not in tools and "Write" not in tools
    assert "Bash" in tools


def test_max_turns_implement_highest():
    assert prompts.max_turns(RunStage.IMPLEMENT) >= prompts.max_turns(RunStage.VERIFY)
```

- [ ] **Step 2: red** → `uv run pytest tests/unit/test_prompts.py -v` (ModuleNotFound).

- [ ] **Step 3: implement** `src/domain/prompts.py`:
```python
"""Pure per-stage prompt + tool policy for the coding agent. No I/O."""

from domain.models import RunStage

_EDIT_TOOLS = ["Read", "Edit", "Write", "Bash"]
_READ_TOOLS = ["Read", "Bash"]


def for_stage(stage: RunStage, task_title: str, acceptance_criteria: list[str],
              body: str = "") -> tuple[str, list[str]]:
    ac = "\n".join(f"- {c}" for c in acceptance_criteria)
    if stage == RunStage.PLAN:
        return (f"Read the ticket and write an implementation plan to plan.md.\n\n"
                f"Ticket: {task_title}\n{body}\n\nAcceptance criteria:\n{ac}",
                ["Read", "Write"])
    if stage == RunStage.IMPLEMENT:
        return (f"Implement this ticket by editing the repository in the working directory.\n\n"
                f"Ticket: {task_title}\n{body}\n\nAcceptance criteria:\n{ac}",
                list(_EDIT_TOOLS))
    if stage == RunStage.VERIFY:
        return (f"Verify the implementation satisfies the acceptance criteria. Run the tests/build. "
                f"Do NOT modify source files.\n\nAcceptance criteria:\n{ac}",
                list(_READ_TOOLS))
    if stage == RunStage.LEARN:
        return (f"Summarise what changed in this run for project memory.", ["Read", "Write"])
    # provision/pr are handled by dedicated activities, not the agent runtime
    return (f"{stage} stage for: {task_title}", ["Read"])


def max_turns(stage: RunStage) -> int:
    return {RunStage.IMPLEMENT: 40, RunStage.VERIFY: 20}.get(stage, 15)
```

- [ ] **Step 4: green** → PASS.
- [ ] **Step 5: commit**
```bash
git add src/domain/prompts.py tests/unit/test_prompts.py
git commit -m "feat: pure per-stage agent prompts + tool policy"
```

---

## Task T2: Pure stream-json parser  (Lane PARSER)

**Files:** Create `src/adapters/runtime/stream_json.py`; Test `tests/unit/test_stream_json.py`.

- [ ] **Step 1: failing test**
```python
# tests/unit/test_stream_json.py
import json

from adapters.runtime.stream_json import parse
from domain.models import RunStage


def _lines(*objs):
    return [json.dumps(o) for o in objs]


def test_parses_progress_and_result_with_cost():
    lines = _lines(
        {"type": "system", "subtype": "init"},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "working on it"}]}},
        {"type": "result", "subtype": "success", "is_error": False,
         "total_cost_usd": 0.42, "result": "done"},
    )
    events, result = parse(lines, RunStage.IMPLEMENT)
    assert any(e.type == "progress" and "working" in e.message for e in events)
    assert events[-1].type == "result"
    assert result.outcome == "ok" and result.cost_usd == 0.42


def test_is_error_maps_to_fail():
    lines = _lines({"type": "result", "is_error": True, "total_cost_usd": 0.1})
    _events, result = parse(lines, RunStage.VERIFY)
    assert result.outcome == "fail"


def test_ignores_blank_and_unknown_lines():
    events, result = parse(["", "not json", json.dumps({"type": "whatever"})], RunStage.PLAN)
    assert result.outcome == "ok"  # default; no result line
    assert events == [] or all(e.type != "result" for e in events)
```

- [ ] **Step 2: red** → ModuleNotFound.

- [ ] **Step 3: implement** `src/adapters/runtime/stream_json.py`:
```python
"""Pure parser for Claude Code `--output-format stream-json` lines."""

import json
from typing import Iterable

from domain.models import RunStage
from domain.runtime import AgentEvent, StageResult


def _assistant_text(obj: dict) -> str:
    content = obj.get("message", {}).get("content", [])
    return " ".join(
        p.get("text", "") for p in content
        if isinstance(p, dict) and p.get("type") == "text"
    ).strip()


def parse(lines: Iterable[str], stage: RunStage) -> tuple[list[AgentEvent], StageResult]:
    events: list[AgentEvent] = []
    result = StageResult(outcome="ok")
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = obj.get("type")
        if kind == "assistant":
            text = _assistant_text(obj)
            if text:
                events.append(AgentEvent(type="progress", stage=stage, message=text[:500]))
        elif kind == "result":
            outcome = "fail" if obj.get("is_error") else "ok"
            result = StageResult(
                outcome=outcome,
                cost_usd=float(obj.get("total_cost_usd") or 0.0),
                artifacts={"result": obj.get("result", "")},
            )
            events.append(AgentEvent(type="result", stage=stage, message="stage complete",
                                     data=result.model_dump()))
    return events, result
```

- [ ] **Step 4: green** → PASS.
- [ ] **Step 5: commit**
```bash
git add src/adapters/runtime/stream_json.py tests/unit/test_stream_json.py
git commit -m "feat: pure claude stream-json parser"
```

---

## Task T3: Settings for the agent runtime  (Lane MODEL)

**Files:** Modify `src/interactors/api/settings.py`; Test `tests/unit/test_settings.py`.

- [ ] **Step 1: failing test** — add:
```python
def test_agent_runtime_defaults():
    from interactors.api.settings import Settings
    s = Settings(_env_file=None)
    assert s.agent_runtime == "auto"
    assert s.agent_model == "claude-sonnet-4-6"
    assert s.claude_max_turns == 30
    assert s.anthropic_api_key is None
```

- [ ] **Step 2: red** → AttributeError.

- [ ] **Step 3: implement** — add to `Settings` (and update the `Literal` import is already present):
```python
    anthropic_api_key: str | None = None
    agent_model: str = "claude-sonnet-4-6"
    claude_max_turns: int = 30
    agent_runtime: Literal["auto", "fake", "claude_code"] = "auto"
```

- [ ] **Step 4: green** → PASS.
- [ ] **Step 5: commit**
```bash
git add src/interactors/api/settings.py tests/unit/test_settings.py
git commit -m "feat: agent-runtime settings (model, max-turns, selector, key)"
```

---

## Task T4: ModelProvider port + Anthropic + Fake  (Lane MODEL)

**Files:** Create `src/adapters/model/__init__.py`, `ports.py`, `anthropic.py`, `fake.py`; Test `tests/unit/test_model_provider.py`.

- [ ] **Step 1: failing test**
```python
# tests/unit/test_model_provider.py
from adapters.model.anthropic import AnthropicProvider
from adapters.model.fake import FakeModelProvider


def test_anthropic_env_and_model():
    p = AnthropicProvider(api_key="sk-test", model="claude-sonnet-4-6")
    assert p.agent_env()["ANTHROPIC_API_KEY"] == "sk-test"
    assert p.model_id() == "claude-sonnet-4-6"


def test_anthropic_env_empty_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert AnthropicProvider(api_key=None).agent_env() == {}


def test_fake_provider():
    f = FakeModelProvider()
    assert f.model_id() == "fake-model"
    assert f.agent_env() == {}
```

- [ ] **Step 2: red** → ModuleNotFound.

- [ ] **Step 3: implement**

`src/adapters/model/__init__.py` (empty). `src/adapters/model/ports.py`:
```python
from typing import Protocol


class ModelProvider(Protocol):
    """Supplies the agent subprocess's model connection (env) + model id.
    AnthropicProvider now; a LiteLLMProvider can drop in later (A5c)."""

    def agent_env(self) -> dict[str, str]: ...
    def model_id(self) -> str: ...
```

`src/adapters/model/anthropic.py`:
```python
import os


class AnthropicProvider:
    """Default ModelProvider: the agent talks directly to Anthropic."""

    def __init__(self, api_key: str | None = None, model: str = "claude-sonnet-4-6"):
        self._api_key = api_key
        self._model = model

    def agent_env(self) -> dict[str, str]:
        key = self._api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        return {"ANTHROPIC_API_KEY": key} if key else {}

    def model_id(self) -> str:
        return self._model
```

`src/adapters/model/fake.py`:
```python
class FakeModelProvider:
    def agent_env(self) -> dict[str, str]:
        return {}

    def model_id(self) -> str:
        return "fake-model"
```

- [ ] **Step 4: green** → PASS.
- [ ] **Step 5: commit**
```bash
git add src/adapters/model tests/unit/test_model_provider.py
git commit -m "feat: ModelProvider port + AnthropicProvider + FakeModelProvider"
```

---

## Task T5: ClaudeCodeRuntime (injectable subprocess)  (Lane RUNTIME)

**Files:** Create `src/adapters/runtime/claude_code.py`; Test `tests/unit/test_claude_code_runtime.py`, `tests/integration/test_claude_code_real.py`.

> Depends on T1 (prompts), T2 (parser), T4 (model). Wave 2.

- [ ] **Step 1: failing test** — fake `spawn` returns an object with `.stdout` (an iterable of stream-json lines), `.wait()`, `.pid`:
```python
# tests/unit/test_claude_code_runtime.py
import json

from adapters.model.fake import FakeModelProvider
from adapters.runtime.claude_code import ClaudeCodeRuntime
from domain.models import RunStage
from domain.runtime import RunContext


class _FakeProc:
    def __init__(self, lines):
        self.stdout = iter(lines)
        self.stderr = iter([])
        self.pid = 4321
        self.returncode = 0
    def wait(self):
        return 0


def _ctx(stage=RunStage.IMPLEMENT):
    return RunContext(run_id="r1", stage=stage, task_title="Add login",
                      acceptance_criteria=["works"], workspace_path="/ws")


def test_run_stage_streams_events_and_result():
    lines = [
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "editing"}]}}),
        json.dumps({"type": "result", "is_error": False, "total_cost_usd": 0.5, "result": "ok"}),
    ]
    captured = {}
    def spawn(argv, **kw):
        captured["argv"] = argv
        captured["cwd"] = kw.get("cwd")
        return _FakeProc(lines)
    rt = ClaudeCodeRuntime(FakeModelProvider(), spawn=spawn)
    events = list(rt.run_stage(_ctx()))
    assert captured["cwd"] == "/ws"
    assert "claude" in captured["argv"][0]
    assert "--output-format" in captured["argv"] and "stream-json" in captured["argv"]
    assert events[-1].type == "result"
    from adapters.runtime.fake import result_of
    assert result_of(events).cost_usd == 0.5


def test_run_stage_fail_when_no_result_event():
    def spawn(argv, **kw):
        return _FakeProc([])  # claude died with no output
    rt = ClaudeCodeRuntime(FakeModelProvider(), spawn=spawn)
    events = list(rt.run_stage(_ctx()))
    from adapters.runtime.fake import result_of
    assert result_of(events).outcome == "fail"
```

- [ ] **Step 2: red** → ModuleNotFound.

- [ ] **Step 3: implement** `src/adapters/runtime/claude_code.py`:
```python
import os
import signal
import subprocess
from typing import Iterator

from adapters.model.ports import ModelProvider
from adapters.runtime import stream_json
from domain import prompts
from domain.runtime import AgentEvent, RunContext, StageResult


class ClaudeCodeRuntime:
    """AgentRuntime backed by the Claude Code CLI as a subprocess in the workspace.
    `spawn` is injectable so tests never launch real claude."""

    def __init__(self, model: ModelProvider, *, spawn=subprocess.Popen):
        self._model = model
        self._spawn = spawn
        self._procs: dict[str, object] = {}

    def run_stage(self, ctx: RunContext) -> Iterator[AgentEvent]:
        body = ctx.prior_artifacts.get("body", "") if ctx.prior_artifacts else ""
        prompt, tools = prompts.for_stage(ctx.stage, ctx.task_title, ctx.acceptance_criteria, body)
        env = {**os.environ, **self._model.agent_env()}
        argv = [
            "claude", "-p", prompt,
            "--output-format", "stream-json", "--verbose",
            "--allowedTools", *tools,
            "--max-turns", str(prompts.max_turns(ctx.stage)),
            "--model", self._model.model_id(),
        ]
        proc = self._spawn(
            argv, cwd=ctx.workspace_path, env=env,
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
            events.append(AgentEvent(type="result", stage=ctx.stage,
                                     message="claude exited without a result", data=fail.model_dump()))
        yield from events

    def cancel(self, run_id: str) -> None:  # pragma: no cover - needs a real process group
        proc = self._procs.get(run_id)
        if proc is not None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
```

- [ ] **Step 4: opt-in real test** `tests/integration/test_claude_code_real.py`:
```python
import os
import shutil
import tempfile

import pytest

from adapters.model.anthropic import AnthropicProvider
from adapters.runtime.claude_code import ClaudeCodeRuntime
from adapters.runtime.fake import result_of
from domain.models import RunStage
from domain.runtime import RunContext

_have = os.environ.get("ANTHROPIC_API_KEY") and shutil.which("claude")


@pytest.mark.skipif(not _have, reason="claude binary / ANTHROPIC_API_KEY not available")
def test_real_plan_stage_runs():
    ws = tempfile.mkdtemp()
    rt = ClaudeCodeRuntime(AnthropicProvider(model="claude-sonnet-4-6"))
    ctx = RunContext(run_id="r1", stage=RunStage.PLAN, task_title="Write a haiku to plan.md",
                     acceptance_criteria=[], workspace_path=ws)
    events = list(rt.run_stage(ctx))
    assert result_of(events).outcome in ("ok", "fail")
```

- [ ] **Step 5: green + commit** → `uv run pytest tests/unit/test_claude_code_runtime.py tests/integration/test_claude_code_real.py -v` (real skips); `uv run ruff check src tests`.
```bash
git add src/adapters/runtime/claude_code.py tests/unit/test_claude_code_runtime.py tests/integration/test_claude_code_real.py
git commit -m "feat: ClaudeCodeRuntime subprocess adapter + opt-in real test"
```

---

## Task T6: Worker auto-selects the runtime  (Lane RUNTIME)

**Files:** Modify `src/interactors/temporal/worker.py`; Test `tests/unit/test_worker_build.py`.

- [ ] **Step 1: failing test** — add:
```python
from interactors.temporal.worker import _build_runtime
from interactors.api.settings import Settings
from adapters.storage.local import LocalStorageAdapter
from adapters.runtime.fake import FakeAgentRuntime
import tempfile


def test_build_runtime_fake_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    s = Settings(_env_file=None, agent_runtime="auto", anthropic_api_key=None)
    rt = _build_runtime(s, LocalStorageAdapter(base_dir=tempfile.mkdtemp()))
    assert isinstance(rt, FakeAgentRuntime)


def test_build_runtime_forced_fake(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    s = Settings(_env_file=None, agent_runtime="fake")
    rt = _build_runtime(s, LocalStorageAdapter(base_dir=tempfile.mkdtemp()))
    assert isinstance(rt, FakeAgentRuntime)


def test_build_runtime_claude_code_when_selected(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _b: "/usr/bin/claude")
    s = Settings(_env_file=None, agent_runtime="claude_code", anthropic_api_key="sk-x")
    rt = _build_runtime(s, LocalStorageAdapter(base_dir=tempfile.mkdtemp()))
    from adapters.runtime.claude_code import ClaudeCodeRuntime
    assert isinstance(rt, ClaudeCodeRuntime)
```
(The existing `test_build_activities_returns_six` stays — with no key it still wires the fake.)

- [ ] **Step 2: red** → `_build_runtime` missing.

- [ ] **Step 3: implement** — in `src/interactors/temporal/worker.py` add imports `import os, shutil` and:
```python
def _build_model_provider(settings):
    from adapters.model.anthropic import AnthropicProvider
    return AnthropicProvider(api_key=settings.anthropic_api_key, model=settings.agent_model)


def _build_runtime(settings, storage):
    choice = settings.agent_runtime
    has_key = bool(settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY"))
    use_claude = choice == "claude_code" or (choice == "auto" and has_key and shutil.which("claude"))
    if use_claude:
        from adapters.runtime.claude_code import ClaudeCodeRuntime
        return ClaudeCodeRuntime(_build_model_provider(settings))
    return FakeAgentRuntime(storage=storage)
```
and change `build_activities` to use it:
```python
def build_activities(database_url: str, profile: str = "local") -> list:
    engine = make_engine(database_url)
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    storage = LocalStorageAdapter(base_dir="data/workspaces")
    from adapters.git.local_git import LocalGit
    from interactors.api.settings import Settings
    settings = Settings()
    git = LocalGit()
    forge = _build_forge(profile)
    runtime = _build_runtime(settings, storage)
    acts = RunActivities(factory, runtime, storage, git, forge)
    return [acts.persist_run_state, acts.record_event, acts.run_stage,
            acts.cleanup_workspace, acts.provision_workspace, acts.open_pr]
```

- [ ] **Step 4: green** → `uv run pytest tests/unit/test_worker_build.py -v` PASS (incl. existing six-activities test); `uv run ruff check src tests`.
- [ ] **Step 5: commit**
```bash
git add src/interactors/temporal/worker.py tests/unit/test_worker_build.py
git commit -m "feat: worker auto-selects ClaudeCodeRuntime vs fake"
```

---

## Task T7: Containerized worker image + compose  (Lane INFRA)

**Files:** Create `infra/worker/Dockerfile`; Modify `docker-compose.yml`, `Makefile`, `CLAUDE.md`; Test `tests/unit/test_worker_dockerfile.py`.

- [ ] **Step 1: failing test** — a lightweight guard that the image + service are wired (no Docker needed to run it):
```python
# tests/unit/test_worker_dockerfile.py
from pathlib import Path


def test_worker_dockerfile_installs_claude_and_git():
    df = Path("infra/worker/Dockerfile").read_text()
    assert "claude-code" in df          # npm i -g @anthropic-ai/claude-code
    assert "git" in df


def test_compose_has_hardened_worker_service():
    compose = Path("docker-compose.yml").read_text()
    assert "worker:" in compose
    assert "no-new-privileges:true" in compose
    assert "cap_drop" in compose
```

- [ ] **Step 2: red** → file/strings missing.

- [ ] **Step 3: implement**

`infra/worker/Dockerfile`:
```dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm i -g @anthropic-ai/claude-code \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY src ./src

RUN useradd -m appuser && mkdir -p /app/data/workspaces && chown -R appuser /app
USER appuser

CMD ["uv", "run", "python", "-m", "interactors.temporal.worker"]
```

Add to `docker-compose.yml` under `services:` (the hardened worker):
```yaml
  worker:
    build: { context: ., dockerfile: infra/worker/Dockerfile }
    depends_on: [postgres, temporal]
    environment:
      YAAH_DATABASE_URL: postgresql+psycopg://yaah:yaah@postgres:5432/yaah
      YAAH_TEMPORAL_ADDRESS: temporal:7233
      YAAH_PROFILE: ${YAAH_PROFILE:-local}
      YAAH_AGENT_RUNTIME: ${YAAH_AGENT_RUNTIME:-auto}
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}
    volumes:
      - workspaces:/app/data/workspaces
    read_only: true
    tmpfs: [/tmp]
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
    mem_limit: 4g
    pids_limit: 512
    restart: unless-stopped
```
Add `workspaces:` under the top-level `volumes:`.

Update `Makefile` `worker` target:
```makefile
worker:
	docker compose up -d --build worker
```
Add a one-line note to `CLAUDE.md` dev commands:
```bash
ANTHROPIC_API_KEY=... docker compose up -d --build worker   # real agent worker (auto-selects claude)
```

- [ ] **Step 4: green** → `uv run pytest tests/unit/test_worker_dockerfile.py -v` PASS; `docker compose config >/dev/null && echo OK`.
- [ ] **Step 5: commit**
```bash
git add infra/worker/Dockerfile docker-compose.yml Makefile CLAUDE.md tests/unit/test_worker_dockerfile.py
git commit -m "feat: containerized worker image + hardened compose service"
```

---

## Task T8: Full verify + integration PR  (Wave 3)

- [ ] **Step 1:** `rm -rf ui/dist && uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=80` → all pass (real-agent + dockerfile-strings tests included; opt-in real skips), ≥80%.
- [ ] **Step 2:** `uv run ruff check src tests` → clean.
- [ ] **Step 3:** Commit fixes; open the integration PR to `main`.

> Coverage note: `ClaudeCodeRuntime.cancel`, `worker.run_worker/main/run`, and any line needing a live `claude`/Docker may use `# pragma: no cover` — never the prompts, parser, model provider, `_build_runtime`, or `run_stage` parse path (all covered offline).

---

## Self-review (resolved)

- **Spec §2 in scope** ↔ ClaudeCodeRuntime (T5), stream_json (T2), prompts (T1), ModelProvider/Anthropic/Fake (T4), worker image+compose (T7), auto-selection (T6), real cost (T2 parser → StageResult). ✅
- **Spec §4 signatures** ↔ `ModelProvider.agent_env/model_id` (T4) used by `ClaudeCodeRuntime` (T5) and `_build_model_provider` (T6); `prompts.for_stage/max_turns` (T1) used by T5; `stream_json.parse` (T2) used by T5; `result_of` reused from `adapters/runtime/fake` (T5 tests). ✅
- **Spec §6 selection** ↔ `_build_runtime` auto/fake/claude_code (T6); tests force fake; CI has no key. ✅
- **Spec §5 containerized worker** ↔ T7 (Dockerfile + hardened compose + Makefile). ✅
- **Spec §8 testing** ↔ pure (T1,T2,T4), monkeypatched subprocess (T5), selection (T6), opt-in real (T5), dockerfile guard (T7). Existing 124 stay on `FakeAgentRuntime`. ✅
- **Type consistency:** `RunContext`/`AgentEvent`/`StageResult` unchanged (domain/runtime.py); `build_activities` still returns 6 activities (T6); `RunActivities` ctor unchanged (runtime swapped, same position). ✅
- **No pipeline/workflow change** — runtime is swapped behind the existing `AgentRuntime` port; PROVISION/PR still handled by A4a activities. ✅
```
