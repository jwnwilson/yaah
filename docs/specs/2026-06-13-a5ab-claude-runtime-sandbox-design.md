# yaah A5a+A5b — Claude Code runtime in a containerized worker (Design)

**Date:** 2026-06-13
**Status:** Approved design, pending implementation plan
**Phase:** A5a+A5b (real agent runtime + local containerized sandbox)
**Depends on:** A1–A4a (all merged to `main`) — Temporal pipeline, `AgentRuntime` port, A4a workspace/git/forge/PR, `StoragePort`.

## 1. Problem & goal

A3/A4a run a *faked* agent: `FakeAgentRuntime` writes a fixed file, then real PROVISION/PR
machinery turns it into a branch/PR. A5a+A5b replaces the fake with a **real Claude Code agent**
that does the actual work, and confines it for local use by **running the Temporal worker inside
a hardened Docker container** — the agent is a `claude` subprocess of that worker, working on the
mounted target repo. This is the v1 success criterion: a real agent produces a reviewed PR.

Simplification chosen over per-run ephemeral sandbox containers: **one containerized worker runs
`claude` directly** (no docker-in-docker, no per-stage `docker run`). The worker container is the
access boundary. Per-run ephemeral isolation is the remote/k8s story (later). Egress proxy /
credential broker / permissions interceptor + audit are **A5c** (deferred).

### A5a+A5b success criterion

> With the worker running in its Docker container and `ANTHROPIC_API_KEY` configured, starting a
> run on a Ready task drives the pipeline with a **real `claude` agent**: it reads the ticket,
> edits the workspace, runs tests, and produces a commit on `agent/<task-id>` that the PR stage
> turns into a branch (local) or PR (remote) — with real per-stage cost from claude's stream-json
> on the run. With no key / no claude, the worker falls back to `FakeAgentRuntime` and every
> existing test stays green.

## 2. Scope

### In scope
- **`ClaudeCodeRuntime`** (`AgentRuntime` impl): spawn `claude -p --output-format stream-json` in
  the workspace per stage, stream events, return `StageResult`; `cancel()` kills the process.
- **Pure `stream_json` parser**: claude stream-json lines → `AgentEvent`s + `StageResult`
  (captures `total_cost_usd`).
- **Pure `domain/prompts.py`**: per-stage prompt text + conservative `--allowedTools`.
- **Model abstraction**: `ModelProvider` port + default `AnthropicProvider` (+ Fake), supplying
  the agent's model env/config. (LiteLLM is a future provider — A5c.)
- **Containerized worker**: `infra/worker/Dockerfile` (python + claude CLI + git + toolchains) and
  a hardened `worker` compose service (non-root, resource limits, workspaces + repo mounts,
  `ANTHROPIC_API_KEY` in env).
- **Runtime auto-selection** in the worker: `ClaudeCodeRuntime` when key + claude available, else
  `FakeAgentRuntime`.
- **Real cost** from stream-json flowed into `StageResult.cost_usd`.

### Out of scope (later)
- Egress proxy / credential broker / zero-secret containers (A5c).
- PreToolUse permission interceptor + audit log (A5c).
- LiteLLM gateway service + virtual keys/budgets (A5c; the `ModelProvider` port makes it a drop-in).
- Per-run ephemeral hardened containers / k8s sandbox (remote story).
- Skills/MCP capability manifest, cross-model plan review, parallel engineers (phase B/C).

## 3. Decisions log

| Decision | Choice | Rationale |
|---|---|---|
| Sandbox model | **Containerized worker runs `claude` directly** | Simplest to build/maintain/debug locally; container is the access boundary; no docker-in-docker |
| Per-run isolation | **Deferred to remote/k8s** | Single-user local doesn't need per-run ephemeral containers |
| Runtime | **`ClaudeCodeRuntime` subprocess** behind the existing `AgentRuntime` port | Drop-in for `FakeAgentRuntime`; pipeline unchanged |
| Model access | **`ModelProvider` port, default `AnthropicProvider`** | "Anthropic now, LiteLLM later easily" — provider yields agent env/config |
| Selection | **auto: claude_code when key+binary present, else fake** | Real agent opt-in by environment; CI/tests stay fake-and-green |
| Tool posture | **static per-stage `--allowedTools`** from `domain/prompts.py` | Bounded blast radius; full interceptor/audit is A5c |
| Cost | **real `total_cost_usd` from stream-json** | Accurate per-stage cost with no extra infra |
| Testing | **pure-unit + monkeypatched subprocess + opt-in real** | 80% gate offline; real path covered when key/claude present |

## 4. Architecture

```
src/
  domain/
    prompts.py            # PURE: for_stage(ctx) -> (prompt_text, allowed_tools[list[str]]); max_turns_for(stage)
  adapters/
    runtime/
      stream_json.py      # PURE: parse(lines: Iterable[str]) -> (list[AgentEvent], StageResult)
      claude_code.py      # ClaudeCodeRuntime(AgentRuntime): spawn claude, stream, parse, return result
      fake.py             # unchanged (default in tests / no-key worker)
    model/
      ports.py            # ModelProvider Protocol
      anthropic.py        # AnthropicProvider (default) — reads Settings; yields agent env + model id
      fake.py             # FakeModelProvider
  interactors/
    temporal/worker.py    # _build_runtime(settings) auto-selects; _build_model_provider(settings)
    api/settings.py       # + anthropic_api_key, agent_model, claude_max_turns, agent_runtime ("auto")
infra/
  worker/Dockerfile       # worker image: python deps + `npm i -g @anthropic-ai/claude-code` + git + node
docker-compose.yml        # `worker` service (non-root, mem/cpu/pids limits, volumes, env), `make worker` -> compose
```

### Ports / key signatures

```python
# adapters/model/ports.py
class ModelProvider(Protocol):
    def agent_env(self) -> dict[str, str]: ...   # e.g. {"ANTHROPIC_API_KEY": "...", "ANTHROPIC_MODEL": "..."}
    def model_id(self) -> str: ...               # alias/model the agent should use

# domain/prompts.py (pure)
def for_stage(stage: RunStage, task_title: str, acceptance_criteria: list[str], body: str) -> tuple[str, list[str]]: ...
def max_turns(stage: RunStage) -> int: ...

# adapters/runtime/claude_code.py
class ClaudeCodeRuntime:                          # implements AgentRuntime structurally
    def __init__(self, model: ModelProvider, *, max_turns_default: int = 30,
                 spawn=subprocess.Popen): ...      # spawn injectable for tests
    def run_stage(self, ctx: RunContext) -> Iterator[AgentEvent]: ...
    def cancel(self, run_id: str) -> None: ...
```

`stream_json.parse` maps claude events: `assistant`/`tool_use` → `AgentEvent(type="progress")`;
periodic → `heartbeat`; `result` (with `total_cost_usd`, `is_error`) → final `AgentEvent
(type="result")` carrying a `StageResult` (`outcome` = `ok`/`fail` from `is_error`, `cost_usd`).

### ClaudeCodeRuntime.run_stage flow
1. `prompt, tools = prompts.for_stage(ctx.stage, ctx.task_title, ctx.acceptance_criteria, body)`.
2. env = `os.environ | model.agent_env()`.
3. `argv = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose",
   "--allowedTools", *tools, "--max-turns", str(prompts.max_turns(ctx.stage)),
   "--model", model.model_id()]`.
4. `proc = spawn(argv, cwd=ctx.workspace_path, env=env, stdout=PIPE, text=True)`; iterate lines,
   yield parsed `AgentEvent`s (heartbeating happens in the activity, unchanged). Final event
   carries the `StageResult`.
5. Non-zero exit with no `result` event → `StageResult(outcome="fail")` + an error event.

## 5. Containerized worker

- `infra/worker/Dockerfile`: base `python:3.12-slim` + node (for claude CLI) + `git`; install
  project deps (`uv sync`); `npm i -g @anthropic-ai/claude-code`; non-root `appuser`; entrypoint
  `python -m interactors.temporal.worker`.
- `docker-compose.yml` `worker` service: `build: infra/worker`; `depends_on` temporal + postgres;
  env `YAAH_DATABASE_URL`, `YAAH_TEMPORAL_ADDRESS=temporal:7233`, `ANTHROPIC_API_KEY`,
  `YAAH_PROFILE`; mounts the workspaces volume and (local profile) the target repo read-write;
  `read_only: true` root fs with a writable workspaces volume; `cap_drop: [ALL]`,
  `security_opt: [no-new-privileges:true]`, `mem_limit`, `pids_limit`, `cpus`.
- `make worker` now runs `docker compose up -d worker` (the host `python -m …` path stays available
  for debugging with the fake runtime).

## 6. Selection & config

- `Settings`: `anthropic_api_key: str | None`, `agent_model: str = "claude-sonnet-4-6"`,
  `claude_max_turns: int = 30`, `agent_runtime: Literal["auto","fake","claude_code"] = "auto"`.
- `worker._build_runtime(settings)`: if `agent_runtime=="fake"` → fake; if `"claude_code"` →
  ClaudeCodeRuntime; if `"auto"` → ClaudeCodeRuntime when `anthropic_api_key` set **and** the
  `claude` binary resolves (`shutil.which`), else fake.
- `worker._build_model_provider(settings)` → `AnthropicProvider(settings)` (future: LiteLLM).
- **Tests never go through `_build_runtime`** — they construct `RunActivities` with
  `FakeAgentRuntime` directly, and CI has no key, so the suite is deterministic and offline.

## 7. Error handling

- claude nonzero exit / no result → run stage `fail` (→ workflow VERIFY-retry or, for other
  stages, `blocked`/`failed`) + an `error` `run_event` with stderr tail (key redacted).
- Subprocess spawn failure (claude missing) in `claude_code` profile → clear `ForgeError`-style
  `RuntimeError`; in `auto` it never selects claude_code without the binary.
- `cancel()` terminates the process group; the existing cleanup activity removes the workspace.
- The API key is only in the worker container env + the child process env; never in run rows,
  events, logs, or prompts.

## 8. Testing (80% gate)

- **Pure unit:** `domain/prompts` (prompt text + tools per stage); `stream_json.parse` over
  canned claude stream-json fixtures (progress + result with `total_cost_usd` and `is_error`);
  `AnthropicProvider.agent_env`/`model_id`.
- **`ClaudeCodeRuntime`:** inject a fake `spawn` returning an object whose stdout yields canned
  stream-json lines; assert it emits the right `AgentEvent`s + `StageResult` (cost parsed),
  and that `cancel()` calls terminate.
- **`_build_runtime` selection:** no key → fake; `agent_runtime="fake"` forced → fake.
- **Opt-in real e2e:** `skipif` no `ANTHROPIC_API_KEY` / no `claude` — runs one real stage in a
  temp workspace and asserts a non-empty result. Not in CI.
- All existing pipeline/activity/workflow tests keep using `FakeAgentRuntime` (124 stay green).

## 9. Risks

- **Image build/size** — claude CLI needs node; image is larger. Pin claude-code + base versions.
- **Determinism of real agent** — handled by the pipeline's VERIFY loop + gates; A5ab doesn't try
  to constrain agent quality, only to run it safely-enough and capture results.
- **Shared worker container** = weaker run-to-run isolation than per-run containers; accepted for
  local single-user, revisited for remote/k8s. Documented.
- **Key handling interim** — env-injected (no broker yet); A5c introduces the zero-secret broker.
  Until then, the worker container is the trust boundary and the key never leaves it.
- **stream-json schema drift** — parser tolerates unknown event types (ignored) and keys off the
  `type`/`subtype` + `total_cost_usd` fields; pinned claude-code version reduces drift.
