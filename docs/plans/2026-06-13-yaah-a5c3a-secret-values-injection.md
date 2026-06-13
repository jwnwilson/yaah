# A5c-3a — Encrypted Secret values + injection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Secrets an encrypted write-only value and inject a granted agent's secrets into the agent process (subprocess env + per-MCP `.mcp.json` env) — without secret values ever entering Temporal history, activity results, run events, or logs.

**Architecture:** A `Cipher` port (FernetCipher, key from Settings); `Secret` gains an `encrypted_value` column with hand-written write-only routes (reads expose `has_value`, never the value); `AgentManifest` gains an activity-local `secret_env`; the `run_stage` activity decrypts granted secrets **in-process** into `secret_env`; `ClaudeCodeRuntime` injects them into the subprocess env + `.mcp.json` `env`.

**Tech Stack:** Python 3.12 · `cryptography` (Fernet, already installed via pyjwt[crypto]) · FastAPI · Temporal · pytest.

**Spec:** `docs/specs/2026-06-13-a5c3a-secret-values-injection-design.md`

**Precondition:** A1–A5c-2 merged to `main`. Key facts: the generic repo's `_to_dto` round-trips **all** non-underscore columns, so a new `encrypted_value` column requires a matching DTO field **and** API responses that omit it. `cryptography.fernet` is importable.

## Conventions
- TDD; `uv run pytest <path> -v`; `rm -rf ui/dist` before the full suite; commit per task with the given message.
- **Security invariant:** secret plaintext is decrypted only inside `run_stage` (in-process) and never appears in activity inputs, activity return values, `run_events`, or logs — tests assert its absence.

## Parallel waves
- **Wave 1 (parallel, disjoint):** CIPHER (T1) ‖ SECRET-MODEL (T2) ‖ MANIFEST (T4).
- **Wave 2 (parallel, disjoint):** API (T3, needs T1+T2) ‖ INJECT (T5 activity → T6 runtime, needs T1+T2+T4).
- **Wave 3:** T7 verify + integration PR.

---

## Task T1: Cipher port + FernetCipher + Settings key  (Lane CIPHER)

**Files:** Create `src/adapters/secrets/__init__.py`, `src/adapters/secrets/cipher.py`; Modify `src/interactors/api/settings.py`; Test `tests/unit/test_cipher.py`, `tests/unit/test_settings.py`.

- [ ] **Step 1: failing test**
```python
# tests/unit/test_cipher.py
import pytest
from cryptography.fernet import Fernet

from adapters.secrets.cipher import FernetCipher


def test_round_trip():
    key = Fernet.generate_key().decode()
    c = FernetCipher(key)
    token = c.encrypt("s3cret")
    assert token != "s3cret"
    assert c.decrypt(token) == "s3cret"


def test_wrong_key_cannot_decrypt():
    token = FernetCipher(Fernet.generate_key().decode()).encrypt("x")
    with pytest.raises(Exception):
        FernetCipher(Fernet.generate_key().decode()).decrypt(token)
```
and add to `tests/unit/test_settings.py`:
```python
def test_secret_key_defaults_none():
    from interactors.api.settings import Settings
    assert Settings(_env_file=None).secret_key is None
```

- [ ] **Step 2: red** → `uv run pytest tests/unit/test_cipher.py -v` (ModuleNotFound).

- [ ] **Step 3: implement** `src/adapters/secrets/__init__.py` (empty) and `src/adapters/secrets/cipher.py`:
```python
from typing import Protocol

from cryptography.fernet import Fernet


class Cipher(Protocol):
    def encrypt(self, plaintext: str) -> str: ...
    def decrypt(self, token: str) -> str: ...


class FernetCipher:
    """Symmetric AEAD via Fernet. `key` is a urlsafe-base64 32-byte Fernet key
    (generate with `Fernet.generate_key().decode()`)."""

    def __init__(self, key: str):
        self._f = Fernet(key.encode() if isinstance(key, str) else key)

    def encrypt(self, plaintext: str) -> str:
        return self._f.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        return self._f.decrypt(token.encode()).decode()
```
and add to `Settings` (`src/interactors/api/settings.py`):
```python
    secret_key: str | None = None
```

- [ ] **Step 4: green** → both test files pass.
- [ ] **Step 5: commit**
```bash
git add src/adapters/secrets/__init__.py src/adapters/secrets/cipher.py src/interactors/api/settings.py tests/unit/test_cipher.py tests/unit/test_settings.py
git commit -m "feat: Cipher port + FernetCipher + secret_key setting"
```

---

## Task T2: Secret encrypted_value (model + column)  (Lane SECRET-MODEL)

**Files:** Modify `src/domain/models.py`, `src/adapters/database/orm.py`; Test `tests/unit/test_repositories.py`.

- [ ] **Step 1: failing test** — add:
```python
def test_secret_roundtrips_encrypted_value():
    from adapters.database.engine import make_engine, make_session_factory
    from adapters.database.orm import Base
    from adapters.database.uow import SqlUnitOfWork
    from domain.models import Secret

    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    uow = SqlUnitOfWork(make_session_factory(engine), required_filters={"owner_id": "u1"})
    with uow.transaction():
        sec = uow.secrets.create(Secret(owner_id="u1", name="GH"))
        assert sec.encrypted_value is None
        stored = uow.secrets.update(sec.id, sec.model_copy(update={"encrypted_value": "tok"}))
    assert stored.encrypted_value == "tok"
```

- [ ] **Step 2: red** → TypeError (`Secret` has no `encrypted_value`).

- [ ] **Step 3: implement**
  - `src/domain/models.py`: add to `Secret`:
    ```python
        encrypted_value: str | None = None
    ```
  - `src/adapters/database/orm.py`: add to `SecretRow`:
    ```python
        encrypted_value: Mapped[str | None] = mapped_column(Text)
    ```

- [ ] **Step 4: green** → PASS.
- [ ] **Step 5: commit**
```bash
git add src/domain/models.py src/adapters/database/orm.py tests/unit/test_repositories.py
git commit -m "feat: Secret encrypted_value (DTO field + column)"
```

---

## Task T3: Write-only secret value API  (Lane API, wave 2)

**Files:** Modify `src/interactors/api/routes/capabilities.py`, `src/interactors/api/deps.py`; Test `tests/integration/test_capabilities_api.py`.

> Needs T1 (cipher) + T2 (column). Replaces the C1 CrudRouter `secrets_router` with hand-written
> routes so responses omit the value.

- [ ] **Step 1: failing test** — add:
```python
def test_secret_value_is_write_only_and_encrypted():
    c = _client()  # existing helper in this file
    sid = c.post("/secrets", json={"name": "GH_TOKEN"}).json()["data"]["id"]
    # read: no value, has_value False
    got = c.get(f"/secrets/{sid}").json()["data"]
    assert "encrypted_value" not in got and got["has_value"] is False
    # set value
    r = c.put(f"/secrets/{sid}/value", json={"value": "ghp_secret"})
    assert r.status_code == 200 and r.json()["data"]["has_value"] is True
    # read again: still no value, has_value True
    got2 = c.get(f"/secrets/{sid}").json()["data"]
    assert "encrypted_value" not in got2 and got2["has_value"] is True
    assert "ghp_secret" not in c.get("/secrets").text  # never serialized in lists either
```
> `_client()` must build the app with a key. Update the file's `_client()` helper (or add one) to
> pass `Settings(_env_file=None, database_url="sqlite:///:memory:", secret_key=Fernet.generate_key().decode())`
> (import `from cryptography.fernet import Fernet`).

- [ ] **Step 2: red** → `has_value`/`/value` missing.

- [ ] **Step 3: implement**

In `src/interactors/api/deps.py` add a cipher dependency:
```python
def cipher(request: Request):
    from adapters.secrets.cipher import FernetCipher
    key = request.app.state.settings.secret_key
    return FernetCipher(key) if key else None
```

In `src/interactors/api/routes/capabilities.py`, **replace** the `secrets_router = CrudRouter(...)`
line with a hand-written router (keep `skills_router` and `mcp_router` as-is). Add imports
`from fastapi import APIRouter, Depends, HTTPException, Query`, `from adapters.database.ports import
UnitOfWork`, `from domain.models import Secret`, `from interactors.api.deps import get_uow, cipher`,
`from interactors.api.envelope import ok`:
```python
def _secret_read(s: Secret) -> dict:
    d = s.model_dump(mode="json")
    d.pop("encrypted_value", None)
    d["has_value"] = s.encrypted_value is not None
    return d


secrets_router = APIRouter(prefix="/secrets", tags=["capabilities"])


@secrets_router.post("", status_code=201)
def create_secret(body: CreateSecret, user_id: str = Depends(current_user_id),
                  uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        created = uow.secrets.create(Secret(owner_id=user_id, **body.model_dump()))
    return ok(_secret_read(created))


@secrets_router.get("")
def list_secrets(page_size: int = Query(100, ge=1, le=200), page_number: int = Query(1, ge=1),
                 uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        page = uow.secrets.list(page_size=page_size, page_number=page_number)
    return ok([_secret_read(s) for s in page.results],
              meta={"total": page.total, "page_size": page.page_size, "page_number": page.page_number})


@secrets_router.get("/{secret_id}")
def get_secret(secret_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        s = uow.secrets.get(secret_id)
    return ok(_secret_read(s))


@secrets_router.patch("/{secret_id}")
def patch_secret(secret_id: str, body: UpdateSecret, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        s = uow.secrets.get(secret_id)
        result = uow.secrets.update(secret_id, s.model_copy(update=body.model_dump(exclude_none=True)))
    return ok(_secret_read(result))


@secrets_router.delete("/{secret_id}")
def delete_secret(secret_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        uow.secrets.delete(secret_id)
    return ok({"deleted": secret_id})


class SetSecretValue(BaseModel):
    value: str


@secrets_router.put("/{secret_id}/value")
def set_secret_value(secret_id: str, body: SetSecretValue,
                     uow: UnitOfWork = Depends(get_uow), c=Depends(cipher)) -> dict:
    if c is None:
        raise HTTPException(status_code=503, detail="secret encryption key not configured")
    with uow.transaction():
        s = uow.secrets.get(secret_id)
        result = uow.secrets.update(secret_id,
                                    s.model_copy(update={"encrypted_value": c.encrypt(body.value)}))
    return ok(_secret_read(result))
```
> `current_user_id` import: add `from interactors.api.auth import current_user_id` (the CrudRouter
> imported it internally; the hand-written create needs it). `app.py` already includes
> `capabilities.secrets_router` — no change needed since the name is unchanged.

- [ ] **Step 4: green** → `uv run pytest tests/integration/test_capabilities_api.py -v` PASS (incl. the C1 secret tests, which still get 201 + a value-free body).
- [ ] **Step 5: commit**
```bash
git add src/interactors/api/routes/capabilities.py src/interactors/api/deps.py tests/integration/test_capabilities_api.py
git commit -m "feat: write-only secret value API (encrypted, reads expose has_value)"
```

---

## Task T4: AgentManifest.secret_env  (Lane MANIFEST)

**Files:** Modify `src/domain/capabilities.py`; Test `tests/unit/test_capabilities.py`.

- [ ] **Step 1: failing test** — add:
```python
def test_manifest_has_secret_env_default_empty():
    from domain.capabilities import AgentManifest
    assert AgentManifest().secret_env == {}
    m = AgentManifest(secret_env={"GH_TOKEN": "x"})
    assert m.secret_env["GH_TOKEN"] == "x"
```

- [ ] **Step 2: red** → TypeError (no `secret_env`).

- [ ] **Step 3: implement** — add to `AgentManifest` in `src/domain/capabilities.py`:
```python
    secret_env: dict[str, str] = {}
```
> Activity-local only: populated in `run_stage`, never serialized into Temporal payloads/results.
> `assemble()` is unchanged (it does not take secret values).

- [ ] **Step 4: green** → PASS.
- [ ] **Step 5: commit**
```bash
git add src/domain/capabilities.py tests/unit/test_capabilities.py
git commit -m "feat: AgentManifest.secret_env (activity-local)"
```

---

## Task T5: Activity decrypts granted secrets in-process  (Lane INJECT, wave 2)

**Files:** Modify `src/interactors/temporal/activities.py`; Test `tests/unit/test_activities.py`.

> Needs T1+T2+T4. The leak-prevention task.

- [ ] **Step 1: failing test** — assert `secret_env` is populated **and** the value never escapes:
```python
def test_run_stage_injects_secret_env_without_leaking():
    import json, tempfile
    from cryptography.fernet import Fernet
    from adapters.database.uow import SqlUnitOfWork
    from adapters.git.fake import FakeGit
    from adapters.forge.fake import FakeGitForge
    from adapters.storage.local import LocalStorageAdapter
    from adapters.secrets.cipher import FernetCipher
    from domain.models import AgentDefinition, Secret, Team
    from interactors.temporal.activities import RunActivities

    factory = _factory()
    run_id = _seed_run(factory)
    key = Fernet.generate_key().decode()
    cipher = FernetCipher(key)
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        team = uow.teams.create(Team(owner_id="u1", name="T"))
        sec = uow.secrets.create(Secret(owner_id="u1", name="GH_TOKEN",
                                        encrypted_value=cipher.encrypt("ghp_TOPSECRET")))
        uow.agents.create(AgentDefinition(team_id=team.id, role="backend", name="E",
                                          model_alias="m", secret_ids=[sec.id]))

    captured = {}
    class _Spy:
        def run_stage(self, ctx):
            captured["ctx"] = ctx
            from domain.runtime import AgentEvent, StageResult
            yield AgentEvent(type="result", stage=ctx.stage, message="ok",
                             data=StageResult(outcome="ok").model_dump())
        def cancel(self, run_id): ...

    recorded = []
    acts = RunActivities(factory, _Spy(), LocalStorageAdapter(base_dir=tempfile.mkdtemp()),
                         FakeGit(), FakeGitForge(), cipher=cipher)
    # capture every event the activity records
    orig = acts.record_event
    acts.record_event = lambda p: recorded.append(p) or orig(p)

    result = acts.run_stage({"run_id": run_id, "owner_id": "u1", "stage": "implement",
                             "task_title": "T", "acceptance_criteria": [], "team_id": team.id})

    assert captured["ctx"].agent.secret_env == {"GH_TOKEN": "ghp_TOPSECRET"}   # injected in-process
    assert "ghp_TOPSECRET" not in json.dumps(result)                          # not in activity result
    assert "ghp_TOPSECRET" not in json.dumps(recorded)                        # not in run_events
```
> Adapt `_factory`/`_seed_run`/`RunActivities` builder to the file's existing helpers; the
> assertions are the point.

- [ ] **Step 2: red** → `RunActivities` has no `cipher` param / `secret_env` empty.

- [ ] **Step 3: implement** — in `src/interactors/temporal/activities.py`:
  - constructor: add `cipher=None` → `self._cipher = cipher`.
  - In `run_stage`, where C2 assembles the manifest (after `agent_manifest = capabilities.assemble(...)`),
    add secret resolution **in the same in-process block**, before building `RunContext`:
    ```python
                    if self._cipher is not None and selected.secret_ids:
                        secret_env = {}
                        for sec_id in selected.secret_ids:
                            try:
                                sec = uow.secrets.get(sec_id)
                                if sec.encrypted_value:
                                    secret_env[sec.name] = self._cipher.decrypt(sec.encrypted_value)
                            except Exception:  # noqa: BLE001 - missing/bad secret: skip, don't fail
                                pass
                        agent_manifest = agent_manifest.model_copy(update={"secret_env": secret_env})
    ```
  - The `RunContext(... agent=agent_manifest ...)` line is unchanged. **Do not** add secret_env to
    `record_event` payloads or the return value. The activity return stays `result_of(events).model_dump()`.
  - Wire the cipher in `worker.build_activities`: build a `FernetCipher(settings.secret_key)` when
    `settings.secret_key` is set, pass `cipher=...` to `RunActivities(...)`. (worker.py edit lives in
    this lane.)

- [ ] **Step 4: green** → `uv run pytest tests/unit/test_activities.py -v` PASS (existing run_stage tests unaffected — no cipher/secret → `secret_env` stays empty).
- [ ] **Step 5: commit**
```bash
git add src/interactors/temporal/activities.py src/interactors/temporal/worker.py tests/unit/test_activities.py
git commit -m "feat: run_stage decrypts granted secrets in-process into secret_env"
```

---

## Task T6: Runtime injects secret_env  (Lane INJECT, wave 2)

**Files:** Modify `src/adapters/runtime/claude_code.py`; Test `tests/unit/test_claude_code_runtime.py`.

- [ ] **Step 1: failing test** — add:
```python
def test_secret_env_injected_into_subprocess_and_mcp():
    import json, os, tempfile
    from adapters.model.fake import FakeModelProvider
    from adapters.skills.fake import FakeSkillFetcher
    from adapters.runtime.claude_code import ClaudeCodeRuntime
    from domain.capabilities import AgentManifest, McpRef
    from domain.models import RunStage
    from domain.runtime import RunContext

    ws = tempfile.mkdtemp()
    man = AgentManifest(allowed_tools=["Read"], secret_env={"GH_TOKEN": "ghp_x"},
                        mcp_servers=[McpRef(name="fs", transport="stdio", command_or_url="npx mcp-fs")])
    ctx = RunContext(run_id="r1", stage=RunStage.IMPLEMENT, task_title="T",
                     workspace_path=ws, agent=man)
    captured = {}
    class _P:
        def __init__(s): s.stdout = iter([json.dumps({"type": "result", "is_error": False, "total_cost_usd": 0})]); s.stderr = iter([]); s.pid = 1
        def wait(s): return 0
    def spawn(argv, **kw):
        captured["env"] = kw.get("env", {})
        return _P()
    list(ClaudeCodeRuntime(FakeModelProvider(), spawn=spawn, skills=FakeSkillFetcher()).run_stage(ctx))
    assert captured["env"].get("GH_TOKEN") == "ghp_x"
    cfg = json.load(open(os.path.join(ws, ".mcp.json")))
    assert cfg["mcpServers"]["fs"]["env"]["GH_TOKEN"] == "ghp_x"
```

- [ ] **Step 2: red** → secret not in env / no `env` in `.mcp.json`.

- [ ] **Step 3: implement** — in `src/adapters/runtime/claude_code.py`:
  - where the env is built (`env = {**os.environ, **self._model.agent_env()}`), merge secret_env when present:
    ```python
            if ctx.agent is not None and ctx.agent.secret_env:
                env = {**env, **ctx.agent.secret_env}
    ```
  - in `_write_mcp_config`, accept the secret env and add an `env` block per server:
    ```python
    def _write_mcp_config(workspace_path: str, servers, secret_env: dict | None = None) -> None:
        import json
        env = secret_env or {}
        mcp = {}
        for s in servers:
            entry = {"command": s.command_or_url} if s.transport == "stdio" else {"url": s.command_or_url}
            if env:
                entry["env"] = dict(env)
            mcp[s.name] = entry
        with open(os.path.join(workspace_path, ".mcp.json"), "w") as f:
            json.dump({"mcpServers": mcp}, f)
    ```
    and update the call site to `_write_mcp_config(ctx.workspace_path, ctx.agent.mcp_servers, ctx.agent.secret_env)`.

- [ ] **Step 4: green** → `uv run pytest tests/unit/test_claude_code_runtime.py -v` PASS (existing tests unaffected — empty secret_env adds nothing).
- [ ] **Step 5: commit**
```bash
git add src/adapters/runtime/claude_code.py tests/unit/test_claude_code_runtime.py
git commit -m "feat: inject secret_env into subprocess env + .mcp.json env"
```

---

## Task T7: Full verify + integration PR  (Wave 3)

- [ ] **Step 1:** `rm -rf ui/dist && uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=80` → all pass, ≥80%.
- [ ] **Step 2:** `uv run ruff check src tests` → clean.
- [ ] **Step 3:** Commit fixes; open the integration PR to `main`.

> Coverage note: only genuinely un-runnable lines (none expected here) use `# pragma: no cover`.
> The leak-prevention assertions in T5 are the security gate — keep them.

---

## Self-review (resolved)

- **Spec §4 cipher** ↔ T1 (Cipher/FernetCipher + secret_key). ✅
- **Spec §4 secret value (write-only)** ↔ T2 (column+DTO), T3 (hand-written routes, `has_value`, `PUT /value`, reads omit value). ✅
- **Spec §4 manifest carry** ↔ T4 (`secret_env`). ✅
- **Spec §4 resolution (no leak)** ↔ T5 (in-process decrypt; explicit absence-in-result/events tests). ✅
- **Spec §4 injection** ↔ T6 (subprocess env + `.mcp.json` env). ✅
- **Spec §5 error handling** ↔ no key → 503 on set (T3) + skip on inject (T5); decrypt failure skipped (T5). ✅
- **Spec §6 testing** ↔ cipher (T1), API write-only (T3), no-leak (T5), injection (T6); existing 164 green (no key in CI → no injection; reads gain only `has_value`). ✅
- **Type consistency:** `Cipher.encrypt/decrypt` used by T3 (encrypt) + T5 (decrypt); `Secret.encrypted_value` set/read across T2/T3/T5; `AgentManifest.secret_env` populated T5, consumed T6; `RunActivities(..., cipher=)` consistent T5 + worker. ✅
- **Repo mapping caveat handled:** `Secret` DTO carries `encrypted_value` (so `_to_dto` round-trips) but every secrets API response strips it via `_secret_read` and exposes `has_value`. ✅
```
