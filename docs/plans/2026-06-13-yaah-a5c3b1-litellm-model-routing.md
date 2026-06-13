# A5c-3b-1 — LiteLLM provider + per-agent model routing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route model traffic through a LiteLLM gateway and make each per-stage agent's `model_alias` the model it runs as — a drop-in for the existing `ModelProvider` port.

**Architecture:** `LiteLLMProvider` (drop-in `ModelProvider`) points claude at the gateway via env; `AgentManifest.model_alias` carries the selected agent's alias; `ClaudeCodeRuntime` uses it as `--model`; `worker._build_model_provider` selects anthropic/litellm/auto; a LiteLLM compose service + config provides the gateway. Anthropic/fake paths stay default so existing tests are untouched.

**Tech Stack:** Python 3.12 · LiteLLM (compose) · FastAPI · Temporal · pytest.

**Spec:** `docs/specs/2026-06-13-a5c3b1-litellm-model-routing-design.md`

**Precondition:** A1–A5c-3a merged to `main`. Mirror: `adapters/model/{ports,anthropic,fake}.py`, `adapters/runtime/claude_code.py` (argv `--model`), `interactors/temporal/worker.py` (`_build_model_provider`/`_build_runtime`), `domain/capabilities.py` (`AgentManifest`/`assemble`), `interactors/api/settings.py`, `docker-compose.yml`.

## Conventions
- TDD; `uv run pytest <path> -v`; `rm -rf ui/dist` before the full suite; commit per task with the given message.
- Default-off: with no LiteLLM settings, `_build_model_provider` returns `AnthropicProvider` and `model_alias` defaults empty → existing behaviour.

## Parallel waves
- **Wave 1 (parallel, disjoint):** PROVIDER (T1) ‖ MANIFEST (T2) ‖ INFRA (T3).
- **Wave 2 (one lane):** WIRING (T4) — runtime `--model` + worker selection (needs T1+T2).
- **Wave 3:** T5 verify + integration PR.

---

## Task T1: LiteLLMProvider + settings  (Lane PROVIDER)

**Files:** Modify `src/interactors/api/settings.py`; Create `src/adapters/model/litellm.py`; Test `tests/unit/test_settings.py`, `tests/unit/test_model_provider.py`.

- [ ] **Step 1: failing test** — add to `tests/unit/test_settings.py`:
```python
def test_model_gateway_defaults():
    from interactors.api.settings import Settings
    s = Settings(_env_file=None)
    assert s.model_gateway == "auto"
    assert s.litellm_base_url is None and s.litellm_api_key is None
```
and to `tests/unit/test_model_provider.py`:
```python
def test_litellm_provider_env_and_model():
    from adapters.model.litellm import LiteLLMProvider
    p = LiteLLMProvider("http://litellm:4000", "sk-virt", default_model="sonnet")
    env = p.agent_env()
    assert env["ANTHROPIC_BASE_URL"] == "http://litellm:4000"
    assert env["ANTHROPIC_API_KEY"] == "sk-virt"
    assert p.model_id() == "sonnet"
```

- [ ] **Step 2: red** → AttributeError / ModuleNotFound.

- [ ] **Step 3: implement**
  - `src/interactors/api/settings.py` add fields (the `Literal` import already exists):
    ```python
        litellm_base_url: str | None = None
        litellm_api_key: str | None = None
        model_gateway: Literal["anthropic", "litellm", "auto"] = "auto"
    ```
  - `src/adapters/model/litellm.py`:
    ```python
    class LiteLLMProvider:
        """ModelProvider that points the agent at a LiteLLM gateway (Anthropic-compatible
        endpoint). model_id() is the default alias; per-agent routing overrides it via the
        manifest's model_alias."""

        def __init__(self, base_url: str, api_key: str, default_model: str = "sonnet"):
            self._base_url = base_url
            self._api_key = api_key
            self._default_model = default_model

        def agent_env(self) -> dict[str, str]:
            return {"ANTHROPIC_BASE_URL": self._base_url, "ANTHROPIC_API_KEY": self._api_key}

        def model_id(self) -> str:
            return self._default_model
    ```

- [ ] **Step 4: green** → both test files pass.
- [ ] **Step 5: commit**
```bash
git add src/interactors/api/settings.py src/adapters/model/litellm.py tests/unit/test_settings.py tests/unit/test_model_provider.py
git commit -m "feat: LiteLLMProvider + model-gateway settings"
```

---

## Task T2: AgentManifest.model_alias  (Lane MANIFEST)

**Files:** Modify `src/domain/capabilities.py`; Test `tests/unit/test_capabilities.py`.

- [ ] **Step 1: failing test** — add:
```python
def test_assemble_sets_model_alias():
    from domain.capabilities import assemble
    from domain.models import AgentDefinition, AgentRole
    agent = AgentDefinition(team_id="t", role=AgentRole.BACKEND, name="E",
                            model_alias="engineer-model")
    man = assemble(agent, [], [])
    assert man.model_alias == "engineer-model"
```

- [ ] **Step 2: red** → AttributeError (`model_alias` not on manifest).

- [ ] **Step 3: implement** — in `src/domain/capabilities.py`: add to `AgentManifest`:
```python
    model_alias: str = ""
```
and in `assemble(...)` include it in the returned `AgentManifest(...)`:
```python
        model_alias=agent.model_alias,
```

- [ ] **Step 4: green** → PASS.
- [ ] **Step 5: commit**
```bash
git add src/domain/capabilities.py tests/unit/test_capabilities.py
git commit -m "feat: AgentManifest carries model_alias"
```

---

## Task T3: LiteLLM compose service + config  (Lane INFRA)

**Files:** Create `infra/litellm/config.yaml`; Modify `docker-compose.yml`, `Makefile`, `CLAUDE.md`; Test `tests/unit/test_litellm_infra.py`.

- [ ] **Step 1: failing test**
```python
# tests/unit/test_litellm_infra.py
from pathlib import Path


def test_litellm_service_in_compose():
    compose = Path("docker-compose.yml").read_text()
    assert "litellm:" in compose
    assert "infra/litellm/config.yaml" in compose


def test_litellm_config_lists_aliases():
    cfg = Path("infra/litellm/config.yaml").read_text()
    for alias in ("lead-model", "engineer-model", "qa-model"):
        assert alias in cfg
```

- [ ] **Step 2: red** → file/strings missing.

- [ ] **Step 3: implement**

`infra/litellm/config.yaml`:
```yaml
model_list:
  - model_name: lead-model
    litellm_params:
      model: anthropic/claude-sonnet-4-6
      api_key: os.environ/ANTHROPIC_API_KEY
  - model_name: engineer-model
    litellm_params:
      model: anthropic/claude-sonnet-4-6
      api_key: os.environ/ANTHROPIC_API_KEY
  - model_name: qa-model
    litellm_params:
      model: anthropic/claude-haiku-4-5-20251001
      api_key: os.environ/ANTHROPIC_API_KEY
  - model_name: sonnet
    litellm_params:
      model: anthropic/claude-sonnet-4-6
      api_key: os.environ/ANTHROPIC_API_KEY
```

Add to `docker-compose.yml` under `services:`:
```yaml
  litellm:
    image: ghcr.io/berriai/litellm:main-v1.55.8
    command: ["--config", "/app/config.yaml", "--port", "4000"]
    ports:
      - "4000:4000"
    volumes:
      - ./infra/litellm/config.yaml:/app/config.yaml:ro
    environment:
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}
      LITELLM_MASTER_KEY: ${LITELLM_MASTER_KEY:-sk-yaah-local}
    restart: unless-stopped
```

Add to `Makefile`:
```makefile
litellm:
	docker compose up -d litellm
```

Add to `CLAUDE.md` dev commands:
```bash
docker compose up -d litellm   # LiteLLM gateway on :4000 (set YAAH_LITELLM_BASE_URL=http://localhost:4000)
```

- [ ] **Step 4: green** → `uv run pytest tests/unit/test_litellm_infra.py -v` PASS; `docker compose config >/dev/null && echo OK`.
- [ ] **Step 5: commit**
```bash
git add infra/litellm/config.yaml docker-compose.yml Makefile CLAUDE.md tests/unit/test_litellm_infra.py
git commit -m "feat: LiteLLM compose service + alias config"
```

---

## Task T4: Runtime uses model_alias + worker selects provider  (Lane WIRING, wave 2)

**Files:** Modify `src/adapters/runtime/claude_code.py`, `src/interactors/temporal/worker.py`; Test `tests/unit/test_claude_code_runtime.py`, `tests/unit/test_worker_build.py`.

> Needs T1 (provider/settings) + T2 (manifest.model_alias).

- [ ] **Step 1: failing tests** — add to `tests/unit/test_claude_code_runtime.py`:
```python
def test_model_alias_overrides_model_flag():
    import json, tempfile
    from adapters.model.fake import FakeModelProvider
    from adapters.skills.fake import FakeSkillFetcher
    from adapters.runtime.claude_code import ClaudeCodeRuntime
    from domain.capabilities import AgentManifest
    from domain.models import RunStage
    from domain.runtime import RunContext

    man = AgentManifest(allowed_tools=["Read"], model_alias="engineer-model")
    ctx = RunContext(run_id="r1", stage=RunStage.IMPLEMENT, task_title="T",
                     workspace_path=tempfile.mkdtemp(), agent=man)
    captured = {}
    class _P:
        def __init__(s): s.stdout = iter([json.dumps({"type": "result", "is_error": False, "total_cost_usd": 0})]); s.stderr = iter([]); s.pid = 1
        def wait(s): return 0
    def spawn(argv, **kw):
        captured["argv"] = argv; return _P()
    list(ClaudeCodeRuntime(FakeModelProvider(), spawn=spawn, skills=FakeSkillFetcher()).run_stage(ctx))
    i = captured["argv"].index("--model")
    assert captured["argv"][i + 1] == "engineer-model"   # alias, not provider default "fake-model"
```
and to `tests/unit/test_worker_build.py`:
```python
def test_build_model_provider_selects_litellm(monkeypatch):
    from interactors.temporal.worker import _build_model_provider
    from interactors.api.settings import Settings
    from adapters.model.litellm import LiteLLMProvider
    s = Settings(_env_file=None, model_gateway="litellm",
                 litellm_base_url="http://litellm:4000", litellm_api_key="sk-x")
    assert isinstance(_build_model_provider(s), LiteLLMProvider)


def test_build_model_provider_auto_falls_back_to_anthropic():
    from interactors.temporal.worker import _build_model_provider
    from interactors.api.settings import Settings
    from adapters.model.anthropic import AnthropicProvider
    s = Settings(_env_file=None, model_gateway="auto", litellm_base_url=None)
    assert isinstance(_build_model_provider(s), AnthropicProvider)
```

- [ ] **Step 2: red** → alias not used / selection missing.

- [ ] **Step 3: implement**
  - `src/adapters/runtime/claude_code.py`: where `--model` is added to argv, compute the model id as:
    ```python
            model_id = self._model.model_id()
            if ctx.agent is not None and ctx.agent.model_alias:
                model_id = ctx.agent.model_alias
    ```
    and use `model_id` in the `"--model", model_id` argv entry (replace the existing
    `self._model.model_id()` there). Keep the `ctx.agent is None` path identical to before.
  - `src/interactors/temporal/worker.py`: replace `_build_model_provider` with the selection logic:
    ```python
    def _build_model_provider(settings):
        gw = settings.model_gateway
        use_litellm = gw == "litellm" or (gw == "auto" and bool(settings.litellm_base_url))
        if use_litellm:
            from adapters.model.litellm import LiteLLMProvider
            return LiteLLMProvider(settings.litellm_base_url or "", settings.litellm_api_key or "",
                                   default_model=settings.agent_model)
        from adapters.model.anthropic import AnthropicProvider
        return AnthropicProvider(api_key=settings.anthropic_api_key, model=settings.agent_model)
    ```

- [ ] **Step 4: green** → `uv run pytest tests/unit/test_claude_code_runtime.py tests/unit/test_worker_build.py -v` PASS (existing tests unaffected: empty alias → provider default; no litellm → anthropic); `uv run ruff check src tests`.
- [ ] **Step 5: commit**
```bash
git add src/adapters/runtime/claude_code.py src/interactors/temporal/worker.py tests/unit/test_claude_code_runtime.py tests/unit/test_worker_build.py
git commit -m "feat: route --model via agent model_alias; worker selects LiteLLM/Anthropic"
```

---

## Task T5: Full verify + integration PR  (Wave 3)

- [ ] **Step 1:** `rm -rf ui/dist && uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=80` → all pass, ≥80%.
- [ ] **Step 2:** `uv run ruff check src tests` → clean.
- [ ] **Step 3:** Commit fixes; open the integration PR to `main`.

---

## Self-review (resolved)

- **Spec §4 LiteLLMProvider** ↔ T1. **settings/selection** ↔ T1 (fields) + T4 (`_build_model_provider`). ✅
- **Spec §4 manifest routing** ↔ T2 (`model_alias`) + T4 (runtime `--model`). ✅
- **Spec §4 infra** ↔ T3 (config + compose + makefile/docs). ✅
- **Spec §6 testing** ↔ provider (T1), manifest (T2), infra guard (T3), runtime alias + selection (T4); existing 172 green (defaults unchanged). ✅
- **Type consistency:** `LiteLLMProvider(base_url, api_key, default_model)` used in T1 test + T4 worker; `AgentManifest.model_alias` set in T2, read in T4; `model_gateway`/`litellm_base_url`/`litellm_api_key` settings consistent T1↔T4. `ModelProvider.agent_env/model_id` interface preserved (LiteLLMProvider matches AnthropicProvider). ✅
- **Default-off invariant:** no litellm settings → AnthropicProvider; empty `model_alias` → provider default; `ctx.agent=None` → unchanged argv. ✅
```
