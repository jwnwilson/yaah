# yaah A5c-3d-2 (C3d-2) — Active PreToolUse interceptor (Design)

**Date:** 2026-06-13
**Status:** Approved design, pending implementation plan
**Phase:** A5c-3d-2 (active tool-call audit + enforcement)
**Depends on:** A1–A5c-3d-1 (all merged to `main`) — `audit_events` + `AuditEvent`/`AuditAction` + `GET /runs/{id}/audit`; C2 `ClaudeCodeRuntime` (composes `--allowedTools`, writes config into the workspace) + `AgentManifest.allowed_tools`; `StoragePort`.

## 1. Problem & goal

C3d-1 records *what each stage's agent was permitted* (passive). C3d-2 records (and enforces)
*what the agent actually tried*: a claude **PreToolUse hook** intercepts every tool call, checks it
against the per-stage agent's effective allowlist (deny-by-default), **allows/denies via exit
code**, and appends each decision to a workspace `audit.jsonl`. After the stage, the `run_stage`
activity ingests that file into `audit_events` as `tool_allowed` / `tool_denied`. Enforcement
happens **outside the model** (spec §7). Tool *inputs* are never recorded (no secret/payload leak);
full output redaction stays C3c.

### C3d-2 success criterion

> When a real agent runs, every tool call produces a `tool_allowed` or `tool_denied` audit event
> on the run (visible via `GET /runs/{id}/audit`), and a call outside the agent's allowlist is
> blocked by the hook (claude does not execute it). No tool input/argument values appear in the
> audit. With the fake runtime / no agent, behaviour is unchanged and existing tests stay green.

## 2. Scope

### In scope
- Pure `domain/permissions.py`: `tool_decision(tool, allowed_tools) -> Decision(allowed, reason)`
  (deny-by-default; matches plain tool names and `mcp__server__tool` grants).
- New `AuditAction` values: `TOOL_ALLOWED`, `TOOL_DENIED`.
- `adapters/runtime/pretooluse_hook.py` — a claude PreToolUse hook (runnable as a module): reads
  the tool call from stdin + allowlist/paths from env, decides, appends to `audit.jsonl`, exits 0/2.
- `ClaudeCodeRuntime`: write `<workspace>/.claude/settings.json` (PreToolUse hook) + set
  `YAAH_*` env when `ctx.agent` is present.
- `run_stage` activity: ingest `runs/{run_id}/audit.jsonl` → `audit_events` (best-effort, in-process).

### Out of scope (later)
- Risk-tier policy (workspace-edit auto / push+install audited / credentials blocked) — keep a flat
  allowlist now (**later**).
- Tool-input / agent-output **redaction** (**C3c**).
- Human-approval-on-deny mid-run (the hook denies autonomously; escalation is later).

## 3. Decisions log

| Decision | Choice | Rationale |
|---|---|---|
| Mode | **Enforce + audit** | Spec §7 "enforced outside the model"; defense-in-depth beyond `--allowedTools` |
| Recorded | **tool name + decision + reason only — never inputs** | Inputs can carry secrets/large payloads |
| Decision logic | **pure `domain/permissions.tool_decision`** | Testable; the hook is a thin adapter |
| Transport | hook → workspace `audit.jsonl` → activity ingests | Secret-free, pre-broker, no Temporal-history leak (in-process ingest) |
| New actions | `tool_allowed` / `tool_denied` | Extends C3d-1's audit cleanly |
| Hook delivery | `<workspace>/.claude/settings.json` + `YAAH_*` env | Per-run config; claude discovers project settings |

## 4. Architecture

```
src/
  domain/
    models.py            # AuditAction += TOOL_ALLOWED, TOOL_DENIED
    permissions.py       # PURE: tool_decision(tool, allowed_tools) -> Decision
  adapters/runtime/
    pretooluse_hook.py   # claude PreToolUse hook: stdin+env -> decide -> audit.jsonl -> exit 0/2
    claude_code.py       # write .claude/settings.json hook + set YAAH_* env when ctx.agent present
  interactors/temporal/
    activities.py        # run_stage: after the runtime returns, ingest audit.jsonl -> audit_events
```

### Pure decision
```python
# domain/permissions.py
class ToolDecision(BaseModel):
    allowed: bool
    reason: str = ""

def tool_decision(tool: str, allowed_tools: list[str]) -> ToolDecision:
    if tool in allowed_tools:
        return ToolDecision(allowed=True, reason="granted")
    # MCP tools: allow if the exact mcp__server__tool is granted (already explicit in allowed_tools)
    return ToolDecision(allowed=False, reason="not in allowlist")
```

### Hook (`adapters/runtime/pretooluse_hook.py`)
- `main()` reads claude's PreToolUse JSON from stdin (`{"tool_name": ..., ...}`), reads env
  `YAAH_ALLOWED_TOOLS` (JSON list), `YAAH_AUDIT_PATH`, `YAAH_RUN_ID`, `YAAH_STAGE`.
- `dec = tool_decision(tool_name, allowed)`; append a line to `YAAH_AUDIT_PATH`:
  `{"tool": tool_name, "decision": "allow"|"deny", "reason": dec.reason, "stage": ..., "ts": ...}`
  (no tool input).
- Exit `0` (allow) or `2` (deny — claude blocks the tool; reason printed to stderr).
- Runnable as `python -m adapters.runtime.pretooluse_hook`; failures default to **allow** + a
  best-effort `error` line (a broken auditor must not brick the agent; enforcement is also backed by
  `--allowedTools`). *(Open to "fail-closed" if preferred — see question in handoff.)*

### Runtime wiring (`ClaudeCodeRuntime`, when `ctx.agent`)
- Write `<workspace>/.claude/settings.json`:
  ```json
  {"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command",
    "command": "python -m adapters.runtime.pretooluse_hook"}]}]}}
  ```
- Set subprocess env: `YAAH_ALLOWED_TOOLS=json(effective tools)`, `YAAH_AUDIT_PATH=<ws>/audit.jsonl`,
  `YAAH_RUN_ID`, `YAAH_STAGE`. (`PYTHONPATH`/cwd already give the hook access to `src` in the worker image.)

### Ingestion (`run_stage` activity)
- After `runtime.run_stage` returns, read `runs/{run_id}/audit.jsonl` via `StoragePort`; for each
  line create an `audit_event` (`action=tool_allowed|tool_denied`, `actor=role`, `stage`,
  `detail={tool, reason}`). Best-effort try/except; never fails the stage; in-process (no Temporal
  payload). Delete/ignore the file afterward.

## 5. Error handling
- Hook can't decide / IO error → **allow** + best-effort error audit line (fail-open; `--allowedTools`
  still constrains). A `denied` decision exits 2 so claude blocks the call.
- Ingestion failure → skipped (audit is observability, not a gate).
- No `ctx.agent` / fake runtime → no hook written, no ingestion → unchanged.

## 6. Testing (80% gate)
- **Pure:** `tool_decision` (granted / not-granted / mcp tool).
- **Hook `main()`:** stdin JSON + env (tmp `audit.jsonl`) → exit 0 for allowed, 2 for denied; jsonl
  line written; **no tool input** in the line.
- **Runtime:** `ctx.agent` → `.claude/settings.json` written with the PreToolUse hook + `YAAH_*`
  env set (fake spawn captures env/files); no agent → no hook.
- **Activity:** a seeded `audit.jsonl` in the run workspace → `run_stage` ingests `tool_allowed`/
  `tool_denied` rows; assert no tool-input leak.
- **Opt-in real:** claude actually invoking the hook (skip without claude).
- Existing 210 stay green.

## 7. Risks
- **claude hook schema/exit-code contract** — pin to the installed claude-code version; the opt-in
  real test guards it; unit tests cover our `main()` directly.
- **Fail-open vs fail-closed** — chosen fail-open (a broken auditor never bricks the agent), with
  `--allowedTools` as the hard backstop. Flip to fail-closed later if policy demands.
- **In-flight worktrees** — `run_stage`/`activities.py` is also touched by other tracks; the
  ingestion addition is small/localized; trivial rebase if needed.
