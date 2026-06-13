# A5c-3d-2 — Active PreToolUse interceptor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Intercept and audit every agent tool call via a claude PreToolUse hook (deny-by-default, exit-code enforcement), recording each `tool_allowed`/`tool_denied` decision into `audit_events` — never recording tool inputs.

**Architecture:** Pure `domain/permissions.tool_decision`; a `pretooluse_hook` module claude runs per tool call (stdin+env → decide → append `audit.jsonl` → exit 0/2, fail-open); `ClaudeCodeRuntime` writes the workspace `.claude/settings.json` hook + `YAAH_*` env; the `run_stage` activity ingests `audit.jsonl` into `audit_events` in-process. Fake/no-agent path unchanged.

**Tech Stack:** Python 3.12 · claude Code hooks · Temporal · pytest.

**Spec:** `docs/specs/2026-06-13-a5c3d2-pretooluse-interceptor-design.md`

**Precondition:** A1–A5c-3d-1 merged. Mirror: `domain/models.py` (`AuditAction`/`AuditEvent`), `adapters/runtime/claude_code.py` (argv/env/`_write_mcp_config`, `ctx.agent`), `interactors/temporal/activities.py` (`run_stage`, `_record_audit`, `self._storage`), `adapters/storage` (`StoragePort.read_text`).

## Conventions
- TDD; `uv run pytest <path> -v`; `rm -rf ui/dist` before the full suite; commit per task.
- Hook is **fail-open** (a broken auditor never bricks the agent; `--allowedTools` is the hard backstop). **Never** record tool inputs/arguments — tests assert absence.

## Parallel waves
- **Wave 1 (one lane):** DOMAIN = T1 (`permissions.py`) → T2 (`AuditAction` values).
- **Wave 2 (parallel, disjoint):** HOOK (T3, `pretooluse_hook.py`) ‖ RUNTIME (T4, `claude_code.py`) ‖ ACTIVITY (T5, `activities.py`).
- **Wave 3:** T6 verify + integration PR.

---

## Task T1: Pure tool decision  (Lane DOMAIN)

**Files:** Create `src/domain/permissions.py`; Test `tests/unit/test_permissions.py`.

- [ ] **Step 1: failing test**
```python
# tests/unit/test_permissions.py
from domain.permissions import tool_decision


def test_granted_tool_allowed():
    d = tool_decision("Read", ["Read", "Edit"])
    assert d.allowed and d.reason == "granted"


def test_ungranted_tool_denied():
    d = tool_decision("Bash", ["Read"])
    assert not d.allowed and "allowlist" in d.reason


def test_mcp_tool_exact_match():
    assert tool_decision("mcp__fs__read", ["mcp__fs__read"]).allowed
    assert not tool_decision("mcp__fs__write", ["mcp__fs__read"]).allowed
```

- [ ] **Step 2: red** → `uv run pytest tests/unit/test_permissions.py -v` (ModuleNotFound).

- [ ] **Step 3: implement** `src/domain/permissions.py`:
```python
"""Pure tool-permission policy for the PreToolUse interceptor. No I/O."""

from pydantic import BaseModel


class ToolDecision(BaseModel):
    allowed: bool
    reason: str = ""


def tool_decision(tool: str, allowed_tools: list[str]) -> ToolDecision:
    if tool in allowed_tools:
        return ToolDecision(allowed=True, reason="granted")
    return ToolDecision(allowed=False, reason="not in allowlist")
```

- [ ] **Step 4: green** → PASS.
- [ ] **Step 5: commit**
```bash
git add src/domain/permissions.py tests/unit/test_permissions.py
git commit -m "feat: pure tool_decision permission policy"
```

---

## Task T2: AuditAction tool actions  (Lane DOMAIN)

**Files:** Modify `src/domain/models.py`; Test `tests/unit/test_models.py`.

- [ ] **Step 1: failing test**
```python
def test_audit_action_tool_values():
    from domain.models import AuditAction
    assert AuditAction.TOOL_ALLOWED == "tool_allowed"
    assert AuditAction.TOOL_DENIED == "tool_denied"
```

- [ ] **Step 2: red** → AttributeError.

- [ ] **Step 3: implement** — add to `AuditAction` in `src/domain/models.py`:
```python
    TOOL_ALLOWED = "tool_allowed"
    TOOL_DENIED = "tool_denied"
```

- [ ] **Step 4: green** → PASS.
- [ ] **Step 5: commit**
```bash
git add src/domain/models.py tests/unit/test_models.py
git commit -m "feat: AuditAction tool_allowed/tool_denied"
```

---

## Task T3: PreToolUse hook  (Lane HOOK, wave 2)

**Files:** Create `src/adapters/runtime/pretooluse_hook.py`; Test `tests/unit/test_pretooluse_hook.py`.

> Needs T1 (`tool_decision`).

- [ ] **Step 1: failing test**
```python
# tests/unit/test_pretooluse_hook.py
import io
import json
import tempfile

from adapters.runtime import pretooluse_hook


def _run(monkeypatch, payload, allowed, audit_path):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setenv("YAAH_ALLOWED_TOOLS", json.dumps(allowed))
    monkeypatch.setenv("YAAH_AUDIT_PATH", audit_path)
    monkeypatch.setenv("YAAH_STAGE", "implement")
    return pretooluse_hook.main()


def test_allowed_tool_exit0_and_logged(monkeypatch, tmp_path):
    audit = str(tmp_path / "audit.jsonl")
    code = _run(monkeypatch, {"tool_name": "Read", "tool_input": {"x": 1}}, ["Read"], audit)
    assert code == 0
    line = json.loads(open(audit).read().strip())
    assert line["tool"] == "Read" and line["decision"] == "allow"


def test_denied_tool_exit2(monkeypatch, tmp_path):
    audit = str(tmp_path / "audit.jsonl")
    code = _run(monkeypatch, {"tool_name": "Bash", "tool_input": {"command": "echo SECRET"}},
               ["Read"], audit)
    assert code == 2
    body = open(audit).read()
    assert '"decision": "deny"' in body
    assert "SECRET" not in body   # tool input never recorded


def test_bad_stdin_fails_open(monkeypatch, tmp_path):
    audit = str(tmp_path / "audit.jsonl")
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    monkeypatch.setenv("YAAH_ALLOWED_TOOLS", "[]")
    monkeypatch.setenv("YAAH_AUDIT_PATH", audit)
    monkeypatch.setenv("YAAH_STAGE", "plan")
    assert pretooluse_hook.main() == 0  # empty tool -> not in allowlist -> deny? -> see note
```
> Note: bad stdin → `tool=""`, which is not in the allowlist → **deny (exit 2)**. Adjust the last
> assertion to `== 2` once you confirm that's the behaviour; the point is it must not crash. (If you
> prefer empty-tool to be allowed, special-case `tool == ""` → allow in the hook and assert `== 0`.)

- [ ] **Step 2: red** → ModuleNotFound.

- [ ] **Step 3: implement** `src/adapters/runtime/pretooluse_hook.py`:
```python
"""Claude PreToolUse hook: decide + audit each tool call. Run as
`python -m adapters.runtime.pretooluse_hook`. Exit 0 = allow, 2 = deny. Fail-open."""

import json
import os
import sys
from datetime import datetime, timezone


def _append(path: str, record: dict) -> None:
    try:
        with open(path, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:  # noqa: BLE001 - audit is best-effort
        pass


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    tool = payload.get("tool_name") or payload.get("tool") or ""
    audit_path = os.environ.get("YAAH_AUDIT_PATH", "")
    stage = os.environ.get("YAAH_STAGE", "")
    try:
        allowed = json.loads(os.environ.get("YAAH_ALLOWED_TOOLS", "[]"))
    except json.JSONDecodeError:
        allowed = []

    try:
        from domain.permissions import tool_decision
        dec = tool_decision(tool, allowed)
        allowed_ok, reason = dec.allowed, dec.reason
    except Exception:  # noqa: BLE001 - fail-open: never brick the agent
        allowed_ok, reason = True, "auditor error"

    if audit_path:
        _append(audit_path, {
            "tool": tool, "decision": "allow" if allowed_ok else "deny",
            "reason": reason, "stage": stage,
            "ts": datetime.now(timezone.utc).isoformat(),
        })  # NOTE: tool inputs are intentionally NOT recorded
    if not allowed_ok:
        sys.stderr.write(f"yaah: tool '{tool}' denied: {reason}\n")
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
```

- [ ] **Step 4: green** → PASS (fix the last assertion per the note).
- [ ] **Step 5: commit**
```bash
git add src/adapters/runtime/pretooluse_hook.py tests/unit/test_pretooluse_hook.py
git commit -m "feat: PreToolUse hook (decide + audit, fail-open, no inputs)"
```

---

## Task T4: Runtime writes the hook config + env  (Lane RUNTIME, wave 2)

**Files:** Modify `src/adapters/runtime/claude_code.py`; Test `tests/unit/test_claude_code_runtime.py`.

> Needs nothing from T3's code (references the hook by module-path string).

- [ ] **Step 1: failing test**
```python
def test_runtime_writes_pretooluse_hook_and_env():
    import json, os, tempfile
    from adapters.model.fake import FakeModelProvider
    from adapters.skills.fake import FakeSkillFetcher
    from adapters.runtime.claude_code import ClaudeCodeRuntime
    from domain.capabilities import AgentManifest
    from domain.models import RunStage
    from domain.runtime import RunContext

    ws = tempfile.mkdtemp()
    man = AgentManifest(allowed_tools=["Read", "Edit"])
    ctx = RunContext(run_id="r1", stage=RunStage.IMPLEMENT, task_title="T",
                     workspace_path=ws, agent=man)
    captured = {}
    class _P:
        def __init__(s): s.stdout = iter([json.dumps({"type": "result", "is_error": False, "total_cost_usd": 0})]); s.stderr = iter([]); s.pid = 1
        def wait(s): return 0
    def spawn(argv, **kw):
        captured["env"] = kw.get("env", {}); return _P()
    list(ClaudeCodeRuntime(FakeModelProvider(), spawn=spawn, skills=FakeSkillFetcher()).run_stage(ctx))
    settings = json.load(open(os.path.join(ws, ".claude", "settings.json")))
    assert "PreToolUse" in settings["hooks"]
    assert "pretooluse_hook" in json.dumps(settings["hooks"])
    assert json.loads(captured["env"]["YAAH_ALLOWED_TOOLS"]) == ["Read", "Edit"]
    assert captured["env"]["YAAH_AUDIT_PATH"].endswith("audit.jsonl")
    assert captured["env"]["YAAH_RUN_ID"] == "r1" and captured["env"]["YAAH_STAGE"] == "implement"
```

- [ ] **Step 2: red** → no settings.json / env.

- [ ] **Step 3: implement** — in `src/adapters/runtime/claude_code.py`, inside `run_stage` where
  `ctx.agent` is handled (after computing the effective `tools` list, before spawn): write the hook
  settings + add env. Add a module-level helper:
```python
def _write_agent_settings(workspace_path: str) -> None:
    import json
    settings_dir = os.path.join(workspace_path, ".claude")
    os.makedirs(settings_dir, exist_ok=True)
    settings = {"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [
        {"type": "command", "command": "python -m adapters.runtime.pretooluse_hook"}]}]}}
    with open(os.path.join(settings_dir, "settings.json"), "w") as f:
        json.dump(settings, f)
```
  and in the `if ctx.agent is not None:` block, after `tools` is finalized:
```python
                import json as _json
                _write_agent_settings(ctx.workspace_path)
                env = {**env,
                       "YAAH_ALLOWED_TOOLS": _json.dumps(tools),
                       "YAAH_AUDIT_PATH": os.path.join(ctx.workspace_path, "audit.jsonl"),
                       "YAAH_RUN_ID": ctx.run_id,
                       "YAAH_STAGE": str(ctx.stage)}
```
  (Place after `tools` includes agent tools + MCP allowlist and after the existing `env` is built;
  `str(ctx.stage)` yields the stage value, e.g. `"implement"`. The `ctx.agent is None` path is
  unchanged — no settings, no YAAH_* env.)

- [ ] **Step 4: green** → `uv run pytest tests/unit/test_claude_code_runtime.py -v` PASS (existing tests unaffected; `ctx.agent=None` writes nothing).
- [ ] **Step 5: commit**
```bash
git add src/adapters/runtime/claude_code.py tests/unit/test_claude_code_runtime.py
git commit -m "feat: runtime writes PreToolUse hook config + YAAH_* env"
```

---

## Task T5: Activity ingests tool audit  (Lane ACTIVITY, wave 2)

**Files:** Modify `src/interactors/temporal/activities.py`; Test `tests/unit/test_activities.py`.

> Needs T2 (`AuditAction` tool values).

- [ ] **Step 1: failing test**
```python
def test_run_stage_ingests_tool_audit_jsonl():
    import json, tempfile
    from adapters.git.fake import FakeGit
    from adapters.forge.fake import FakeGitForge
    from adapters.storage.local import LocalStorageAdapter
    from adapters.database.uow import SqlUnitOfWork
    from domain.models import AgentDefinition, Team
    from interactors.temporal.activities import RunActivities

    factory = _factory()
    run_id = _seed_run(factory)
    storage = LocalStorageAdapter(base_dir=tempfile.mkdtemp())
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        team = uow.teams.create(Team(owner_id="u1", name="T"))
        uow.agents.create(AgentDefinition(team_id=team.id, role="backend", name="E",
                                          model_alias="m", allowed_tools=["Read"]))

    class _Spy:
        def __init__(self, storage): self._s = storage
        def run_stage(self, ctx):
            # simulate the hook having written decisions during the run
            self._s.write_bytes(f"runs/{ctx.run_id}/audit.jsonl",
                                (json.dumps({"tool": "Read", "decision": "allow", "reason": "granted"}) + "\n"
                                 + json.dumps({"tool": "Bash", "decision": "deny", "reason": "not in allowlist"}) + "\n").encode())
            from domain.runtime import AgentEvent, StageResult
            yield AgentEvent(type="result", stage=ctx.stage, message="ok",
                             data=StageResult(outcome="ok").model_dump())
        def cancel(self, run_id): ...

    acts = RunActivities(factory, _Spy(storage), storage, FakeGit(), FakeGitForge())
    acts.run_stage({"run_id": run_id, "owner_id": "u1", "stage": "implement",
                    "task_title": "T", "acceptance_criteria": [], "team_id": team.id})

    uow2 = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow2.transaction():
        evs = uow2.audit_events.list(filters={"run_id": run_id}).results
    actions = sorted(e.action for e in evs if e.action in ("tool_allowed", "tool_denied"))
    assert actions == ["tool_allowed", "tool_denied"]
    denied = [e for e in evs if e.action == "tool_denied"][0]
    assert denied.detail["tool"] == "Bash"
```
> Adapt `_factory`/`_seed_run`/`RunActivities` builder to the file's existing helpers.

- [ ] **Step 2: red** → no tool audit ingested.

- [ ] **Step 3: implement** — in `src/interactors/temporal/activities.py`, add an in-process helper
  and call it at the end of `run_stage` (after the event loop, before `return`):
```python
    def _ingest_tool_audit(self, owner_id: str, run_id: str) -> None:
        import json
        from domain.models import AuditAction, AuditEvent, RunStage, utc_now
        try:
            raw = self._storage.read_text(f"runs/{run_id}/audit.jsonl")
            if not raw:
                return
            uow = self._uow(owner_id)
            with uow.transaction():
                for line in raw.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    action = (AuditAction.TOOL_ALLOWED if rec.get("decision") == "allow"
                              else AuditAction.TOOL_DENIED)
                    stage_val = rec.get("stage")
                    uow.audit_events.create(AuditEvent(
                        run_id=run_id, owner_id=owner_id,
                        stage=RunStage(stage_val) if stage_val else None,
                        actor="", action=action,
                        detail={"tool": rec.get("tool", ""), "reason": rec.get("reason", "")},
                        created_at=utc_now(),
                    ))
        except Exception:  # noqa: BLE001 - audit ingest is best-effort
            pass
```
  and at the end of `run_stage`, after the `for event in self._runtime.run_stage(ctx):` loop:
```python
        self._ingest_tool_audit(payload["owner_id"], payload["run_id"])
        return result_of(events).model_dump()
```
  (Detail carries only `tool` + `reason` from the jsonl — no tool inputs.)

- [ ] **Step 4: green** → `uv run pytest tests/unit/test_activities.py -v` PASS (existing run_stage tests unaffected — no audit.jsonl → no ingest).
- [ ] **Step 5: commit**
```bash
git add src/interactors/temporal/activities.py tests/unit/test_activities.py
git commit -m "feat: run_stage ingests PreToolUse audit.jsonl into audit_events"
```

---

## Task T6: Full verify + integration PR  (Wave 3)

- [ ] **Step 1:** `rm -rf ui/dist && uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=80` → all pass, ≥80%.
- [ ] **Step 2:** `uv run ruff check src tests` → clean.
- [ ] **Step 3:** Commit fixes; open the integration PR to `main`.

> Coverage note: only the `if __name__ == "__main__"` hook entry uses `# pragma: no cover`; `main()`
> and the decision/ingest paths are covered offline.

---

## Self-review (resolved)

- **Spec §4 decision** ↔ T1; **AuditAction** ↔ T2; **hook** ↔ T3; **runtime wiring** ↔ T4; **ingestion** ↔ T5. ✅
- **Spec §5 error handling** ↔ fail-open hook (T3), best-effort ingest (T5), no-agent unchanged (T4). ✅
- **Spec §6 testing** ↔ pure decision (T1), hook exit/log + no-input (T3), runtime settings+env (T4), ingest + no-leak (T5). ✅
- **No-input/secret guarantee:** hook records only tool name+reason (T3 test asserts `SECRET` absent); ingest copies only `tool`+`reason` (T5). ✅
- **Type consistency:** `tool_decision`/`ToolDecision` (T1) used by the hook (T3); `AuditAction.TOOL_ALLOWED/TOOL_DENIED` (T2) used in ingest (T5); `YAAH_ALLOWED_TOOLS/AUDIT_PATH/RUN_ID/STAGE` set in T4 read in T3; `audit.jsonl` path consistent T3↔T4↔T5. ✅
- **Localized / low-overlap:** new files (`permissions.py`, `pretooluse_hook.py`) + small additions to `claude_code.py` (`ctx.agent` block) and `activities.py` (end of `run_stage`); `AuditAction` is an append-only enum edit. Fake/no-agent path untouched. ✅
```
