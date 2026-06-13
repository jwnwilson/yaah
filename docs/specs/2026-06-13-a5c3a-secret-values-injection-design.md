# yaah A5c-3a (C3a) — Encrypted Secret values + injection (Design)

**Date:** 2026-06-13
**Status:** Approved design, pending implementation plan
**Phase:** A5c-3a (first slice of A5c-3 — the credential foundation)
**Depends on:** A1–A5c-2 (all merged to `main`) — C1 `Secret` registry (reference-only), C2 manifest/`.mcp.json`/runtime composition.

## 1. Problem & goal

C1 modelled `Secret` as a reference only (no value); C2 composes granted MCP servers into
`.mcp.json` but **without credentials**, so anything needing auth is configured-but-dead. C3a
gives `Secret` an **encrypted, write-only value**, and makes the runtime **resolve a granted
agent's secrets and inject them** into the agent process (subprocess env + per-MCP `env` in
`.mcp.json`) so granted MCP servers/tools actually authenticate. Secret values are decrypted
**inside the activity** and handed straight to the in-process runtime — they never enter Temporal
inputs/history, run events, or logs. The egress broker (substitution toward approved hosts),
response/log **redaction**, and private-skill git creds remain **C3c**.

### C3a success criterion

> I can set a secret's value via a write-only API (it's stored encrypted and never returned on
> read). An agent granted that secret runs with it available as an env var, and a granted MCP
> server that declares it gets it in its `.mcp.json` `env` block — so the server authenticates.
> The value appears in **no** workflow input, activity result, run event, or log line.

## 2. Scope

### In scope
- **Encryption**: a Fernet-based cipher with a key from Settings/env (`YAAH_SECRET_KEY`).
- **`Secret` value**: encrypted column; **write-only** set endpoint; reads never return the value
  (expose `has_value` instead).
- **Resolution + injection**: the `run_stage` activity decrypts the selected agent's granted
  `secret_ids` locally and passes values to the in-process `ClaudeCodeRuntime`, which injects them
  as subprocess **env vars** and into each granted MCP server's `.mcp.json` **`env`** block.
- **Leak prevention**: secret values never appear in workflow inputs, activity return values,
  `run_events`, or logs (enforced by where resolution happens + tests).

### Out of scope (later C3 slices)
- Egress proxy / credential broker + injection only toward approved hosts (**C3c**).
- Response/log **redaction** of agent-echoed secrets (**C3c**).
- Private-skill / arbitrary-git credential helpers (**C3c**).
- LiteLLM gateway / model routing (**C3b**); capability/tool audit log (**C3d**).
- Secret rotation/versioning, KMS/envelope encryption (later; the cipher port makes it a swap).

## 3. Decisions log

| Decision | Choice | Rationale |
|---|---|---|
| Cipher | **Fernet (`cryptography`) + key from `Settings`/env** behind a small `Cipher` port | Standard symmetric AEAD; KMS later swaps behind the port |
| Read model | **Write-only** — set value via API; reads expose `has_value` only, never the plaintext | Spec §7 "secrets write-only"; never return plaintext |
| Where decrypted | **In the `run_stage` activity (worker), in-process** | Keeps values out of Temporal history/payloads |
| Injection targets | **Subprocess env + `.mcp.json` `env`** | Smallest path that authenticates MCP/agent now; broker is C3c |
| Manifest carry | secret values travel in the **activity-local** `AgentManifest.secret_env`, never returned | In-process only; activity result/events exclude them |
| Missing key | if `YAAH_SECRET_KEY` unset → secrets simply not injected (warning event), run continues | Local dev without secrets still works |

## 4. Architecture

```
src/
  adapters/secrets/
    __init__.py
    cipher.py            # Cipher port + FernetCipher (encrypt/decrypt) ; key from Settings
  domain/
    models.py            # Secret gains has_value (computed/derived for reads); value stays out of the DTO read shape
    capabilities.py      # AgentManifest gains secret_env: dict[str,str] = {} (activity-local)
  adapters/database/
    orm.py               # SecretRow gains encrypted_value: Text|None
    repository / secrets # unchanged generic repo
  interactors/api/
    settings.py          # + secret_key: str | None
    routes/capabilities.py  # secrets: write-only value endpoint; read schema hides value
  interactors/temporal/
    activities.py        # run_stage: decrypt granted secrets -> manifest.secret_env (in-process)
  adapters/runtime/claude_code.py  # inject secret_env into subprocess env + per-MCP .mcp.json env
```

### Cipher port
```python
# adapters/secrets/cipher.py
class Cipher(Protocol):
    def encrypt(self, plaintext: str) -> str: ...
    def decrypt(self, token: str) -> str: ...

class FernetCipher:
    def __init__(self, key: str): ...        # key = a urlsafe base64 32-byte Fernet key
```

### Secret value: write-only
- `SecretRow.encrypted_value: Mapped[str | None]`.
- Domain `Secret` read DTO stays value-free; add a derived `has_value: bool` for responses.
- API (in `capabilities.py`, alongside the existing secrets CrudRouter):
  - `PUT /secrets/{id}/value` `{value: str}` → encrypt with the `Cipher`, store; returns
    `{id, has_value: true}`. (Hand-written route; the value never round-trips on read.)
  - The existing `GET /secrets[/{id}]` responses **omit** `encrypted_value` and include `has_value`.
- Settings: `secret_key: str | None` (env `YAAH_SECRET_KEY`); a Cipher dependency builds
  `FernetCipher(secret_key)` when set.

### Resolution + injection (no Temporal leak)
- `run_stage` activity (already selects the agent + assembles the manifest in C2): additionally,
  for the selected agent's `secret_ids`, load each `Secret` row, `cipher.decrypt(encrypted_value)`,
  and populate **`manifest.secret_env[name] = value`** — all inside the activity, in-process. The
  manifest is attached to the local `RunContext` and passed to `self._runtime.run_stage(ctx)`; it
  is **not** an activity input, **not** in the activity's return value, and **not** in any
  `run_event`.
- `ClaudeCodeRuntime`: when `ctx.agent.secret_env` is non-empty, merge it into the subprocess
  `env`; when writing `.mcp.json`, add an `env` block to each server from `secret_env` (the server
  declares which it needs via its config — for C3a, inject all granted secret_env into each granted
  server's `env`; per-server scoping refines in C3c).

## 5. Error handling
- No `YAAH_SECRET_KEY` → `Cipher` absent → setting a value returns 503/409 with a clear message;
  injection is skipped with a warning `run_event` ("secrets unavailable: no key"). Run continues.
- Decrypt failure (wrong key/corrupt token) → warning event, that secret skipped (not fatal).
- Secret values are **never** placed in `run_events`, the activity return dict, or log statements;
  a redaction pass over agent output is **C3c** (out of scope here).

## 6. Testing (80% gate)
- **Cipher unit:** `FernetCipher.encrypt`/`decrypt` round-trip; wrong key fails to decrypt.
- **API:** `PUT /secrets/{id}/value` stores encrypted (DB column not plaintext); `GET` never
  returns the value and reports `has_value`; no-key → clear error.
- **Activity:** with `YAAH_SECRET_KEY` set + a granted secret with a value, `run_stage` populates
  `ctx.agent.secret_env` (spy runtime) and the value is **absent** from the activity's return dict
  and any recorded `run_event` (assert explicitly).
- **Runtime:** `secret_env` merged into the subprocess env (fake spawn captures env) and into
  `.mcp.json` `env`; empty `secret_env` → A5ab/C2 behavior unchanged.
- All existing 164 tests stay green (no key in CI → injection skipped; `Secret` reads unchanged
  shape apart from the additive `has_value`).

## 7. Risks
- **Leak surface** — the one rule (decrypt only in-activity, never serialize) is enforced by tests
  asserting absence in results/events; reviewers must guard it.
- **Key management** — env key is interim (single-user); KMS later behind the `Cipher` port. If the
  key is lost/rotated, stored values become undecryptable (documented; rotation is later).
- **Per-server secret scoping** — C3a injects all granted secrets into each granted MCP server's
  env (coarse); C3c's broker tightens to per-host/per-server.
