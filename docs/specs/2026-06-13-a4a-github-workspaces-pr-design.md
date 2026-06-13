# yaah A4a — GitHub App + Workspaces + real PR stage (Design)

**Date:** 2026-06-13
**Status:** Approved design, pending implementation plan
**Phase:** A4a (first slice of A4 execution-plane work)
**Depends on:** A1/A1.5/A2/A3 (all merged to `main`) — Temporal pipeline, `StoragePort`, `FakeAgentRuntime`.

## 1. Problem & goal

A3 runs a faked pipeline whose PROVISION and PR stages are stubs — no real workspace, no
commit, no PR. A4a makes the **workspace and PR real** while the agent is still faked:
provision a real per-run workspace, let the (faked) IMPLEMENT stage write a real file into it,
commit to an `agent/<task-id>` branch, and either **finalize a local branch** (local profile)
or **open a real GitHub PR via a GitHub App** (remote profile). This turns the board's run into
a reviewable branch/PR now, ahead of the real coding agent (A5).

Sandbox container hardening (A4b) and the egress proxy / credential broker (A4c) are **out of
scope** — they only become exercisable when a real agent executes inside the container (A5).

### A4a success criterion

> On the **local** profile, a run produces a real `agent/<task-id>` branch (off the project's
> repo) containing a committed file from the faked IMPLEMENT stage, visible in your editor; the
> PR stage records the branch on the run. On the **remote** profile, the harness mints a GitHub
> App installation token, pushes the branch, and opens a real PR — its URL stored on the run and
> shown in the ticket panel. All offline tests stay green via fakes; the real GitHub path has an
> opt-in integration test.

## 2. Scope

### In scope
- **`GitPort`** + Local implementation (init/clone, branch, commit, push, diff) + Fake.
- **`GitForgePort`** + `GitHubApp` implementation (mint installation token, open PR) + Fake.
- **Pure `domain/scm.py`**: branch-name policy (`agent/<task-id>`) + PR-body assembly.
- **Real PROVISION**: provision a per-run workspace (storage prefix `runs/{run_id}/`), and
  populate it per profile — `LocalWorktreeWorkspace` (git worktree off the project's local repo)
  or `GitCloneWorkspace` (fresh clone using a GitHub App token).
- **Real PR stage**: commit the workspace diff to `agent/<task-id>`; local → finalize the
  branch + record it; remote → push + open PR + record `pr_url`.
- **FakeAgentRuntime change**: IMPLEMENT writes a real deterministic file into the workspace via
  `StoragePort` so the commit/PR is non-empty.
- **Profile selection** (`Settings.profile` local|remote) wires the right impls in the worker.
- **GitHub App creds from Settings/env** (app id, private key, installation id).

### Out of scope (later)
- Hardened Docker sandbox lifecycle (A4b) and egress proxy / credential broker (A4c).
- Real Claude Code runtime + LiteLLM (A5) — runtime stays `FakeAgentRuntime`.
- Encrypted Secret store + Secrets UI (phase C) — creds come from env for now.
- Permissions/PreToolUse interceptor + audit log (lands with the real runtime, A5).
- Branch protection ruleset automation (configured on GitHub out-of-band; documented only).

## 3. Decisions log

| Decision | Choice | Rationale |
|---|---|---|
| Port structure | **`GitPort` + `GitForgePort`**, each with real + fake impls | Clean split (local git vs forge API); both fakeable; mirrors `StoragePort` |
| Workspace | **No domain workspace port**; PROVISION/PR activities compose `StoragePort` + `GitPort` + `GitForgePort` | Consistent with the A3 storage refactor ("workspace = storage + adapters") |
| Profiles | **Both**, profile-selected | Local worktree dev loop + remote GitHub PR (spec deployment table) |
| Fake output | **IMPLEMENT writes a real file via `StoragePort`** | Non-empty, reviewable commit/PR |
| GitHub creds | **Settings/env now**, Secrets UI later (phase C) | Single-user; minimal surface; tokens still per-run, never persisted |
| Testing | **Fakes (+ local bare repo) for CI; opt-in real GitHub test** | 80% gate stays green offline; real path still has coverage when creds present |
| Branch/PR policy | **pure `domain/scm.py`** | Deterministic, unit-testable, no I/O |

## 4. Architecture

```
src/
  domain/
    scm.py            # PURE: branch_name(task_id) -> "agent/<task-id>"; pr_title/pr_body(run, task)
  adapters/
    git/
      ports.py        # GitPort Protocol
      local_git.py    # LocalGit (subprocess `git`) — clone/worktree/branch/commit/push/diff
      fake.py         # FakeGit — in-memory/temp-dir, records calls; deterministic
    forge/
      ports.py        # GitForgePort Protocol
      github_app.py    # GitHubApp — mint installation token (JWT->token), open PR (httpx)
      fake.py         # FakeGitForge — records token mints + PRs, returns canned pr_url
    storage/…         # unchanged (StoragePort + LocalStorageAdapter)
    runtime/fake.py   # FakeAgentRuntime — IMPLEMENT now writes a file via StoragePort
  interactors/
    temporal/
      activities.py   # PROVISION + PR activities compose storage/git/forge; persist branch/pr_url
      worker.py       # wires Git/Forge/Storage impls by Settings.profile
      workflows.py    # unchanged stage order; PR stage records branch/pr_url on the run
    api/settings.py   # + github_app_id / github_private_key / github_installation_id / repo fields
```

### Ports

```python
# adapters/git/ports.py
class GitPort(Protocol):
    def prepare(self, *, repo_ref: str, workspace_path: str, branch: str) -> None: ...
        # local profile: `git worktree add` off repo_ref onto a new branch at workspace_path
        # remote profile: `git clone` repo_ref into workspace_path, checkout new branch
    def commit_all(self, workspace_path: str, message: str) -> bool: ...   # returns False if no diff
    def push(self, workspace_path: str, branch: str, *, token: str | None = None) -> None: ...
    def current_branch(self, workspace_path: str) -> str: ...

# adapters/forge/ports.py
class GitForgePort(Protocol):
    def installation_token(self) -> str: ...                 # short-lived; never persisted
    def open_pull_request(self, *, head: str, base: str, title: str, body: str) -> str: ...  # -> pr_url
```

### Profile wiring (worker)
- **local**: `LocalGit` with `prepare` = `git worktree add` off `project.local_path`; PR stage
  commits + records the branch (no push, no forge). `GitForgePort` = a no-op/Fake.
- **remote**: `LocalGit` with `prepare` = clone `project.repo_url` using a token from
  `GitHubApp.installation_token()`; PR stage pushes + `GitHubApp.open_pull_request(...)`.

## 5. Pipeline integration (Temporal activities)

- **PROVISION activity** (now real): `workspace = storage.local_path("runs/{run_id}")`;
  `git.prepare(repo_ref=<local_path|repo_url>, workspace_path=workspace, branch=scm.branch_name(task_id))`;
  record a `run_event` (`stage_started`/artifact). For remote, mint the token first.
- **IMPLEMENT** (faked): `FakeAgentRuntime` writes `runs/{run_id}/<file>` via `StoragePort`
  into the workspace so there's a diff.
- **PR activity** (now real): `git.commit_all(workspace, scm.commit_message(...))`; if local →
  record `branch` on the run; if remote → `git.push(..., token)` then
  `forge.open_pull_request(head=branch, base=default, title=scm.pr_title(...),
  body=scm.pr_body(...))` and persist `pr_url`. Emits `run_events`.
- The existing `persist_run_state` activity is extended to also set `branch` / `pr_url`
  (already columns on `runs`). Workflow stage order is unchanged; the merge gate still applies.

## 6. Error handling

- Git/forge calls behind ports with typed domain errors (`GitError`, `ForgeError`); activity
  retry policies cap attempts; a failed PROVISION/PR → run `failed` (or `blocked`) + an `error`
  `run_event` with the real message. No secrets in messages/logs (token redaction in `GitHubApp`).
- `commit_all` returning False (no diff) → PR stage records "no changes" and finishes without a
  PR (doesn't happen in normal A4a runs because the fake writes a file).
- Installation tokens are minted per run, held only in the activity, never written to the run row,
  events, or logs.

## 7. Testing (80% gate)

- **Unit:** `domain/scm.py` (branch name, PR body); `FakeGit` / `FakeGitForge`; `FakeAgentRuntime`
  file-write; `LocalGit` against a **temp bare repo** (real `git` subprocess, no network).
- **Workflow (`WorkflowEnvironment`):** PROVISION→IMPLEMENT→PR produces a branch (local) and a
  `pr_url` (remote) using `FakeGit` + `FakeGitForge`; asserts run row `branch`/`pr_url` set.
- **API/integration:** ticket panel run shows `branch`/`pr_url` (run serialization already covers
  the columns).
- **Opt-in real test:** a `@pytest.mark.skipif(no creds)` GitHub App test that mints a token and
  opens a PR against a fixture repo (env-gated; skipped in CI/offline).
- Network-bound lines in `github_app.py` may use `# pragma: no cover` where they require live
  GitHub (mirrors A3's temporal client convention).

## 8. Settings / config

`Settings` gains: `github_app_id: str | None`, `github_private_key: str | None` (PEM or path),
`github_installation_id: str | None`, and a default base branch (`github_base_branch: str =
"main"`). `profile` (existing) selects local vs remote wiring. README/CLAUDE.md note the GitHub
App setup (install on the repo, `contents`+`pull_requests` write) and the env vars.

## 9. Risks

- **`git` subprocess** portability — pin to the system `git`; `LocalGit` shells out with explicit
  args (no shell string interpolation). Worktree cleanup on terminal states reuses the A3
  `cleanup_workspace` activity (`storage.delete_directory` + `git worktree prune`).
- **Token leakage** — tokens only in-activity; `GitHubApp` redacts; never in URLs (use the
  credential-via-header/helper form, not `https://x-access-token:TOKEN@…` in stored remotes).
- **Local profile needs a real local repo** at `project.local_path`; PROVISION validates it and
  fails the run with a clear error if absent.
- **A4b/A4c deferred** means the faked agent runs un-sandboxed on the host in A4a — acceptable
  because it's a *fake* doing deterministic file writes; the real, sandboxed agent is A5.
