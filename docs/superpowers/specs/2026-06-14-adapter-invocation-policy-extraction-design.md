# Adapter cleanup: extract Claude invocation policy into the domain

**Date:** 2026-06-14
**Status:** Approved (focused scope)
**Branch:** to be created on a worktree

## Problem

The instruction that prompted this work: *"There is too much in the adapter
folder; it should be for generic logic to interact with external services. Look
for opportunities to move logic to the domain folder and lib folder."*

## Assessment (evidence-based)

The adapter folder is **leaner than the premise suggests** — ~1540 lines across
~40 files, none over 210 lines, and the pure business logic has *already* been
extracted into `domain/`:

- `domain/prompts.py` — per-stage prompt + tool policy
- `domain/permissions.py` — `tool_decision` (the PreToolUse hook is a thin shell)
- `domain/refinement.py` — proposal shapes + validation
- `domain/scm.py` — branch/commit/PR naming
- `domain/runtime.py` — `AgentEvent` / `StageResult` / `RunContext`

`docs/architecture.md` is explicit about a subtlety that governs this work:
**pure ≠ domain.** Ports co-locate with their adapter; `lib/` is only for
app-agnostic reusable infra; and translation between an external system's wire
format and the domain legitimately lives in adapters (the anti-corruption layer).

That reframes the apparent "pure logic in adapters" candidates:

| File | Pure? | Verdict |
|------|-------|---------|
| `runtime/stream_json.py` | yes | **Keep** — anti-corruption translation of Claude Code's `stream-json` wire format. Moving it to domain would pull external-tool format knowledge into the domain. |
| `refinement/anthropic.py` `_TOOL` schema | yes | **Keep** — the Anthropic API tool-call contract, an external concern. |
| `database/*` | mixed | **Keep** — SQLAlchemy-specific; the architecture doc mandates this placement. |
| `secrets/cipher.py`, `skills/fetcher.py`, `git/`, `forge/`, `model/`, `storage/`, `notify/` | mostly I/O | **Keep** — genuine I/O adapters. |

There is **little to nothing** that genuinely belongs in `lib/` (it is for
app-agnostic infra; everything here is yaah-specific).

## The one genuine opportunity

`adapters/runtime/claude_code.py` (`run_stage`, lines 65–117) interleaves **pure
invocation policy** with subprocess I/O and JSON file writes:

- resolving the tool allowlist (stage defaults → per-agent override → MCP allowlists)
- model-alias resolution
- the `YAAH_*` audit env block
- constructing the `.claude/settings.json` and `.mcp.json` dicts
  (`_write_agent_settings` / `_write_mcp_config`)

That policy is currently untestable without mocking `subprocess`. Extracting it
into a pure domain function makes it directly unit-testable and shrinks the
adapter to true orchestration.

## Design

### New domain module — `domain/agent_invocation.py` (pure, no I/O)

```python
class AgentInvocation(BaseModel):
    argv: list[str]                      # full claude CLI command
    env_extra: dict[str, str] = {}       # YAAH_* + secret_env to merge over os.environ + model env
    files: dict[str, str] = {}           # relpath -> JSON content (.claude/settings.json, .mcp.json)
    skills: list[tuple[str, str, str]] = []   # (name, source, dest) the adapter must fetch
    mcp_config_path: str | None = None   # set when --mcp-config is appended


def build_invocation(ctx: RunContext, *, model_id: str) -> AgentInvocation:
    ...
```

`build_invocation` absorbs the pure decisions currently inlined in `run_stage`:

- stage prompt/tools lookup — delegates to `prompts.for_stage` / `prompts.max_turns`
- per-agent tool allowlist (empty → stage-default fallback) + MCP `tool_allowlist` merge
- model-alias override (caller passes the already-resolved `model_id`)
- `settings.json` dict (PreToolUse hook) and `.mcp.json` dict construction,
  emitted as `files` entries (relative paths → JSON strings)
- the `YAAH_ALLOWED_TOOLS` / `YAAH_AUDIT_PATH` / `YAAH_RUN_ID` / `YAAH_STAGE`
  env block plus `secret_env`, emitted as `env_extra`
- `skills` as `(name, source, dest)` triples for the adapter to fetch

The no-agent path (`ctx.agent is None`) emits no `files`, no `env_extra`, no
skills — matching today's behavior exactly.

### Adapter `claude_code.py` shrinks to orchestration

```python
def run_stage(self, ctx):
    model_id = ctx.agent.model_alias if (ctx.agent and ctx.agent.model_alias) else self._model.model_id()
    inv = build_invocation(ctx, model_id=model_id)

    events_pre = []
    for name, source, dest in inv.skills:
        try:
            self._skills.fetch(source, dest)
        except Exception as exc:  # noqa: BLE001 - skip a bad skill, don't fail the stage
            events_pre.append(AgentEvent(type="progress", stage=ctx.stage,
                                         message=f"skill '{name}' skipped: {exc}"))
    for relpath, content in inv.files.items():
        path = os.path.join(ctx.workspace_path, relpath)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
    env = {**os.environ, **self._model.agent_env(), **inv.env_extra}
    proc = self._spawn(inv.argv, cwd=ctx.workspace_path, env=env, ...)
    # stream_json.parse + fail-if-no-result (unchanged)
```

`cancel()` is unchanged. `stream_json.py` is unchanged.

The skill skip message is preserved exactly (`"skill '<name>' skipped: <exc>"`)
because `skills` triples carry the name — the adapter never parses paths.

### What stays put (anti-corruption layers)

`stream_json.py`, `refinement/anthropic.py` `_TOOL`, and all
DB/git/forge/model/secrets/storage/notify adapters.

## Testing

- **New** `tests/unit/test_agent_invocation.py` — pure tests for
  `build_invocation`, no `subprocess`: each stage; no-agent vs agent;
  tool override; empty-tools fallback to stage defaults; MCP allowlist merge;
  no-MCP path; model alias; `secret_env`; `YAAH_*` env block; `settings.json`
  and `.mcp.json` content; skills list shape.
- **Unchanged** `tests/unit/test_claude_code_runtime.py` — remains the adapter
  integration contract (argv/env/files observed via `run_stage`). All existing
  assertions must stay green with no edits. This is the regression guard proving
  behavior is preserved.
- Coverage gate (80%) must still pass; the extracted pure module is fully
  covered by the new unit tests.

## Non-goals (explicitly out of scope)

- Moving `stream_json.py`, the `_TOOL` schema, or any anti-corruption translator
  into `domain/` or `lib/`.
- Relocating `pretooluse_hook.py` to `interactors/`.
- Any change to the database, git, forge, model, secrets, storage, or notify
  adapters.
- Any `lib/` additions.

## Risks

- **Behavioral drift in argv/env/file order or content.** Mitigated by leaving
  `test_claude_code_runtime.py` untouched as the contract; if any assertion
  there breaks, the refactor changed behavior and must be corrected.
- **Skill-fetch timing.** Today skills are fetched mid-assembly; the new flow
  fetches before spawn. No observable effect; the bad-skill-skipped test still
  holds.
