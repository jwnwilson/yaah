# yaah A5c-3b-1 (C3b-1) — LiteLLM provider + per-agent model routing (Design)

**Date:** 2026-06-13
**Status:** Approved design, pending implementation plan
**Phase:** A5c-3b-1 (LiteLLM routing; budgets are C3b-2)
**Depends on:** A1–A5c-3a (all merged to `main`) — `ModelProvider` port + `AnthropicProvider`, `ClaudeCodeRuntime` model env, C2 per-stage agent selection + `AgentManifest`, `AgentDefinition.model_alias`.

## 1. Problem & goal

Model access is hard-wired to one Anthropic model. Each `AgentDefinition` already has a
`model_alias`, but nothing uses it. C3b-1 routes model traffic through a **LiteLLM gateway** and
makes the **per-stage agent's `model_alias`** the model the agent runs as — so lead/engineer/QA can
use different models, all behind one gateway with logical aliases. It's a drop-in for the existing
`ModelProvider` port. Budgets/caps are C3b-2 (cost is already captured per stage/run).

### C3b-1 success criterion

> With LiteLLM configured, a run's IMPLEMENT stage uses the engineer agent's `model_alias` and PLAN
> uses the lead's — each resolved by LiteLLM to its mapped provider/model — with claude pointed at
> the gateway via base_url + a virtual key. With nothing configured, behaviour is unchanged
> (Anthropic/fake) and all existing tests stay green.

## 2. Scope

### In scope
- **`LiteLLMProvider`** (`ModelProvider` drop-in): `agent_env()` → gateway `base_url` + virtual key;
  `model_id()` → default alias.
- **Per-agent routing**: `AgentManifest.model_alias` (from the selected agent); `ClaudeCodeRuntime`
  uses it as `--model` when present.
- **Provider selection**: `Settings.model_gateway` (`anthropic`|`litellm`|`auto`) + LiteLLM config;
  `worker._build_model_provider` picks.
- **Infra**: a LiteLLM `docker-compose` service + `infra/litellm/config.yaml` + Makefile/docs.

### Out of scope (later)
- Budgets / caps / pause-on-breach + spend dashboard (**C3b-2** / phase C).
- Per-alias virtual keys per run, model registry UI/`ModelAlias` table (phase C).
- Egress broker / redaction (**C3c**).

## 3. Decisions log

| Decision | Choice | Rationale |
|---|---|---|
| Routing carrier | **`AgentManifest.model_alias`** (per-stage) | The agent already has `model_alias`; per-stage routing needs it on the manifest |
| Model id precedence | `ctx.agent.model_alias` if set, else `model.model_id()` | Per-agent override; provider default as fallback |
| Gateway access | claude env `ANTHROPIC_BASE_URL` + `ANTHROPIC_API_KEY=<virtual key>` | claude CLI routes to LiteLLM transparently |
| Selection | `model_gateway: anthropic\|litellm\|auto` (default auto) | auto → LiteLLM when `litellm_base_url` set, else Anthropic; CI stays offline |
| Cost | **unchanged** (stream-json `total_cost_usd`) | already captured; LiteLLM server-side spend is C3b-2's lever |

## 4. Architecture

```
src/
  adapters/model/
    ports.py            # ModelProvider (unchanged)
    anthropic.py        # AnthropicProvider (unchanged)
    litellm.py          # LiteLLMProvider (new)
    fake.py             # FakeModelProvider (unchanged)
  domain/capabilities.py  # AgentManifest gains model_alias; assemble() copies agent.model_alias
  adapters/runtime/claude_code.py  # --model uses ctx.agent.model_alias when present
  interactors/temporal/worker.py   # _build_model_provider selects by settings.model_gateway
  interactors/api/settings.py      # litellm_base_url, litellm_api_key, model_gateway
infra/litellm/config.yaml          # model_list: aliases -> providers
docker-compose.yml                 # `litellm` service
```

### LiteLLMProvider
```python
# adapters/model/litellm.py
class LiteLLMProvider:
    def __init__(self, base_url: str, api_key: str, default_model: str = "sonnet"):
        ...
    def agent_env(self) -> dict[str, str]:
        return {"ANTHROPIC_BASE_URL": self._base_url, "ANTHROPIC_API_KEY": self._api_key}
    def model_id(self) -> str:
        return self._default_model
```

### Manifest + runtime
- `AgentManifest.model_alias: str = ""`; `assemble(agent, ...)` sets `model_alias=agent.model_alias`.
- `ClaudeCodeRuntime.run_stage`: the `--model` value is `ctx.agent.model_alias or self._model.model_id()`
  (when `ctx.agent` exists and its alias is non-empty, route to that alias; else provider default).

### Selection (worker)
```python
def _build_model_provider(settings):
    gw = settings.model_gateway
    use_litellm = gw == "litellm" or (gw == "auto" and settings.litellm_base_url)
    if use_litellm:
        from adapters.model.litellm import LiteLLMProvider
        return LiteLLMProvider(settings.litellm_base_url, settings.litellm_api_key or "",
                               default_model=settings.agent_model)
    from adapters.model.anthropic import AnthropicProvider
    return AnthropicProvider(api_key=settings.anthropic_api_key, model=settings.agent_model)
```
Settings: `litellm_base_url: str | None = None`, `litellm_api_key: str | None = None`,
`model_gateway: Literal["anthropic","litellm","auto"] = "auto"`.

### Infra
- `infra/litellm/config.yaml`: a `model_list` mapping aliases (e.g. `lead-model`, `engineer-model`,
  `qa-model`, `sonnet`) to providers (Anthropic via `os.environ/ANTHROPIC_API_KEY`).
- `docker-compose.yml` `litellm` service (`ghcr.io/berriai/litellm`, version-pinned per spec §9),
  mounting the config, exposing the gateway port, `ANTHROPIC_API_KEY` in env.
- `make litellm` / docs note.

## 5. Error handling
- `model_gateway=litellm` but no `litellm_base_url` → clear config error at worker build; `auto`
  silently falls back to Anthropic.
- Unknown alias at the gateway → LiteLLM returns an error; the stage's claude exits non-zero →
  existing `fail` path (run_event + StageResult fail). No special handling here.

## 6. Testing (80% gate)
- **`LiteLLMProvider`**: `agent_env` returns base_url + key; `model_id` default.
- **`AgentManifest.model_alias`** + `assemble` copies `agent.model_alias`.
- **Runtime**: with `ctx.agent.model_alias="engineer-model"`, `--model engineer-model` in argv
  (fake spawn); empty alias → provider default; `ctx.agent=None` unchanged.
- **`_build_model_provider`**: litellm when configured / auto-fallback to anthropic.
- **Infra guard**: `docker-compose.yml` has a `litellm` service; `infra/litellm/config.yaml` parses.
- Existing 172 tests green (no LiteLLM config → Anthropic/fake; `model_alias` defaults empty).

## 7. Risks
- **claude→LiteLLM compatibility** — claude CLI must accept an Anthropic-compatible base_url;
  LiteLLM exposes an Anthropic-compatible endpoint. Pin LiteLLM version (spec §9, post-supply-chain).
  Covered by the opt-in real test (gateway up + key).
- **Alias drift** — aliases in `config.yaml` must match agents' `model_alias`; mismatch → run fails
  loudly (acceptable; a model registry/validation is phase C).
- **Virtual keys** — single shared key now; per-run virtual keys + budgets are C3b-2.
