# Parallel Same-Role Engineers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the lead dispatch N same-role engineers who work one ticket concurrently in isolated git worktrees, whose branches are deterministically merged back into the task branch, with a merge conflict becoming a lead re-plan.

**Architecture:** Generalize the existing orchestrator dispatch loop. A role appearing K times in the lead's `dispatches` spawns K instanced `AgentWorkflow` actors, each in its own worktree/branch, run concurrently via `asyncio.gather`. After the wave, each engineer's work is committed to its branch and an `integrate_branches` activity merges them into `agent/<task>` in the main worktree; a conflict is fed back to the lead, which re-dispatches the conflicting engineer. Temporal stays the durable executor; all merge logic is deterministic git.

**Tech Stack:** Python 3.12, Temporal (`temporalio`), Pydantic v2, SQLAlchemy, pytest. Spec: `docs/specs/2026-06-15-parallel-engineers-design.md`.

**Conventions (read before starting):**
- Run tests with `uv run pytest <path> -q`. Full gate: `make coverage` (80% min) + `uv run ruff check src tests`.
- Domain code is pure (no I/O). Activities are the only DB/FS writers. Workflows are deterministic.
- Immutable Pydantic updates via `model_copy(update={...})`.
- Each phase is one PR off the latest `main`, in a git worktree. Commit per task.

---

## Phase 1 — Enabling plumbing (PR 1)

Additive only — new git/activity/storage capabilities, unit-tested, **not yet wired into the workflow**. Behavior is unchanged; `make coverage` stays green. This de-risks Phase 2.

### Task 1.1: `GitPort.prepare` accepts a `base` ref (branch a worktree off an arbitrary ref)

Today `prepare` (worktree mode) runs `git worktree add -b <branch> <ws>` with `cwd=repo_ref`, branching off the repo's HEAD. Engineer worktrees must branch off `agent/<task>`, so add an optional `base`.

**Files:**
- Modify: `src/adapters/git/ports.py` (the `prepare` Protocol method)
- Modify: `src/adapters/git/local_git.py:28-41` (`prepare`)
- Modify: `src/adapters/git/fake.py` (`prepare`)
- Test: `tests/unit/test_local_git.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_local_git.py  (append)
def test_prepare_worktree_branches_off_base():
    bare = _bare_repo_with_commit()
    g = LocalGit()
    base_ws = tempfile.mkdtemp()
    g.prepare(repo_ref=bare, workspace_path=base_ws, branch="agent/t1", mode="clone")
    (Path(base_ws) / "base.txt").write_text("on task branch")
    assert g.commit_all(base_ws, "task work") is True
    g.push(base_ws, "agent/t1")
    # a worktree off agent/t1 must contain base.txt
    eng_ws = tempfile.mkdtemp()
    g.prepare(repo_ref=base_ws, workspace_path=eng_ws,
              branch="agent/t1__backend-1-0", mode="worktree", base="agent/t1")
    assert (Path(eng_ws) / "base.txt").exists()
    assert g.current_branch(eng_ws) == "agent/t1__backend-1-0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_local_git.py::test_prepare_worktree_branches_off_base -q`
Expected: FAIL with `TypeError: prepare() got an unexpected keyword argument 'base'`.

- [ ] **Step 3: Implement — add `base` to the port**

```python
# src/adapters/git/ports.py  — update the prepare signature
def prepare(
    self, *, repo_ref: str, workspace_path: str, branch: str,
    mode: Literal["worktree", "clone"], base: str | None = None,
    token: str | None = None,
) -> None: ...
```

```python
# src/adapters/git/local_git.py  — replace prepare()
def prepare(
    self, *, repo_ref: str, workspace_path: str, branch: str,
    mode: Literal["worktree", "clone"], base: str | None = None,
    token: str | None = None,
) -> None:
    if mode == "worktree":
        args = ["worktree", "add", "-b", branch, workspace_path]
        if base is not None:
            args.append(base)  # branch off this ref instead of HEAD
        self._run(args, cwd=repo_ref)
    else:
        self._run([*self._auth_args(token), "clone", repo_ref, workspace_path])
        self._run([*_AUTHOR, "checkout", "-b", branch], cwd=workspace_path)
```

```python
# src/adapters/git/fake.py  — replace prepare()
def prepare(
    self, *, repo_ref: str, workspace_path: str, branch: str,
    mode: Literal["worktree", "clone"], base: str | None = None,
    token: str | None = None,
) -> None:
    self.prepared.append((repo_ref, workspace_path, branch, mode, base))
    self._branch = branch
```

> Note: `FakeGit.prepared` tuples grow a 5th element (`base`). Search tests for `.prepared` and update any positional assertions (e.g. `prepared[0][2] == "agent/t1"` still holds; `len(prepared[0])` becomes 5).

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_local_git.py tests/unit/test_activities.py -q`
Expected: PASS (fix any `.prepared` arity assertions surfaced).

- [ ] **Step 5: Commit**

```bash
git add src/adapters/git tests/unit/test_local_git.py
git commit -m "feat: GitPort.prepare accepts a base ref for worktree branching"
```

### Task 1.2: `GitPort.merge_branch` + `has_commits_ahead`

Deterministic merge of one branch into the current worktree branch, conflict surfaced (aborting on conflict); plus an ahead-of-base check for `open_pr`.

**Files:**
- Modify: `src/adapters/git/ports.py`
- Modify: `src/adapters/git/local_git.py`
- Modify: `src/adapters/git/fake.py`
- Create: `src/domain/scm.py` already exists — add a `MergeResult` DTO to `src/domain/orchestration/core.py` (pure)
- Test: `tests/unit/test_local_git.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_local_git.py  (append)
def _commit_file(g, ws, name, content, msg):
    (Path(ws) / name).write_text(content)
    assert g.commit_all(ws, msg) is True

def test_merge_branch_fast_forward_and_ahead():
    bare = _bare_repo_with_commit()
    g = LocalGit()
    main_ws = tempfile.mkdtemp()
    g.prepare(repo_ref=bare, workspace_path=main_ws, branch="agent/t1", mode="clone")
    assert g.has_commits_ahead(main_ws, "main") is False
    eng_ws = tempfile.mkdtemp()
    g.prepare(repo_ref=main_ws, workspace_path=eng_ws,
              branch="agent/t1__e0", mode="worktree", base="agent/t1")
    _commit_file(g, eng_ws, "a.txt", "A", "eng work")
    res = g.merge_branch(main_ws, branch="agent/t1__e0")
    assert res.ok is True and res.conflict_files == []
    assert (Path(main_ws) / "a.txt").exists()
    assert g.has_commits_ahead(main_ws, "main") is True

def test_merge_branch_conflict_aborts_clean():
    bare = _bare_repo_with_commit()
    g = LocalGit()
    main_ws = tempfile.mkdtemp()
    g.prepare(repo_ref=bare, workspace_path=main_ws, branch="agent/t1", mode="clone")
    _commit_file(g, main_ws, "c.txt", "from-main", "main change")
    eng_ws = tempfile.mkdtemp()
    g.prepare(repo_ref=main_ws, workspace_path=eng_ws,
              branch="agent/t1__e0", mode="worktree", base="agent/t1")
    _commit_file(g, eng_ws, "c.txt", "from-eng", "eng change")  # conflicts on c.txt
    res = g.merge_branch(main_ws, branch="agent/t1__e0")
    assert res.ok is False and "c.txt" in res.conflict_files
    # worktree is NOT left in a conflicted/merging state
    import subprocess
    st = subprocess.run(["git", "-C", main_ws, "status", "--porcelain"],
                        capture_output=True, text=True).stdout
    assert "UU" not in st  # no unmerged entries
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/unit/test_local_git.py -k "merge_branch or ahead" -q`
Expected: FAIL (`AttributeError: 'LocalGit' object has no attribute 'merge_branch'`).

- [ ] **Step 3: Implement — `MergeResult` DTO (pure domain)**

```python
# src/domain/orchestration/core.py  (append near the other DTOs)
class MergeResult(BaseModel):
    """Outcome of merging one branch into the current worktree branch."""
    ok: bool
    branch: str = ""
    conflict_files: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Implement — git methods**

```python
# src/adapters/git/ports.py  (add to the Protocol)
def merge_branch(self, workspace_path: str, *, branch: str) -> "MergeResult": ...
def has_commits_ahead(self, workspace_path: str, base: str) -> bool: ...
```
(Import `MergeResult` from `domain.orchestration` at the top of `ports.py`.)

```python
# src/adapters/git/local_git.py  (append methods; import MergeResult)
def merge_branch(self, workspace_path: str, *, branch: str) -> MergeResult:
    proc = subprocess.run(
        ["git", *_AUTHOR, "merge", "--no-ff", "-m", f"merge {branch}", branch],
        cwd=workspace_path, capture_output=True, text=True,
    )
    if proc.returncode == 0:
        return MergeResult(ok=True, branch=branch)
    files = self._run(["diff", "--name-only", "--diff-filter=U"], cwd=workspace_path)
    self._run(["merge", "--abort"], cwd=workspace_path)  # never leave a conflicted tree
    return MergeResult(ok=False, branch=branch,
                       conflict_files=[f for f in files.splitlines() if f.strip()])

def has_commits_ahead(self, workspace_path: str, base: str) -> bool:
    out = self._run(["rev-list", "--count", f"{base}..HEAD"], cwd=workspace_path)
    return int(out.strip() or "0") > 0
```
(`_AUTHOR` is the existing module constant for commit author flags; reuse it.)

```python
# src/adapters/git/fake.py  (append; add ctor knobs)
# In __init__: self._merge_conflict_on: tuple[str, ...] = ()  ; self._ahead = False
def merge_branch(self, workspace_path: str, *, branch: str) -> "MergeResult":
    from domain.orchestration import MergeResult
    if branch in self._merge_conflict_on:
        return MergeResult(ok=False, branch=branch, conflict_files=["conflict.txt"])
    self.merged_branches.append((workspace_path, branch))
    return MergeResult(ok=True, branch=branch)

def has_commits_ahead(self, workspace_path: str, base: str) -> bool:
    return self._ahead or bool(self.merged_branches)
```
Add `self.merged_branches: list[tuple] = []` and the two knobs to `FakeGit.__init__`, plus
ctor params `merge_conflict_on=(), ahead=False`.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/unit/test_local_git.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/adapters/git src/domain/orchestration/core.py tests/unit/test_local_git.py
git commit -m "feat: GitPort.merge_branch (conflict-aborting) + has_commits_ahead"
```

### Task 1.3: `provision_engineer_workspace` activity

**Files:**
- Modify: `src/interactors/temporal/activities.py` (new activity near `provision_workspace`)
- Test: `tests/unit/test_activities.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_activities.py  (append; reuse _factory/_seed_run/_acts/_storage helpers)
def test_provision_engineer_workspace_branches_off_task():
    factory = _factory()
    run_id = _seed_run(factory)
    git = FakeGit()
    acts = _acts(factory, git=git)
    acts.provision_engineer_workspace({
        "run_id": run_id, "owner_id": "u1", "profile": "local",
        "repo_ref": "/repo", "base": "agent/task1",
        "branch": "agent/task1__backend-1-0", "workspace_key": f"runs/{run_id}/w/backend-1-0",
    })
    repo_ref, ws, branch, mode, base = git.prepared[0]
    assert branch == "agent/task1__backend-1-0" and base == "agent/task1" and mode == "worktree"
    assert ws.endswith(f"runs/{run_id}/w/backend-1-0")
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/unit/test_activities.py::test_provision_engineer_workspace_branches_off_task -q`
Expected: FAIL (`AttributeError: ... has no attribute 'provision_engineer_workspace'`).

- [ ] **Step 3: Implement the activity**

```python
# src/interactors/temporal/activities.py  (add after provision_workspace)
@activity.defn(name="provision_engineer_workspace")
def provision_engineer_workspace(self, payload: dict) -> dict:
    workspace = self._storage.local_path(payload["workspace_key"])
    self._git.prepare(repo_ref=payload["repo_ref"], workspace_path=workspace,
                      branch=payload["branch"], mode="worktree", base=payload["base"])
    self.record_event({"run_id": payload["run_id"], "owner_id": payload["owner_id"],
                       "stage": "implement", "type": "stage_started",
                       "message": f"engineer workspace {payload['branch']}"})
    return {"outcome": "ok"}
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_activities.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/interactors/temporal/activities.py tests/unit/test_activities.py
git commit -m "feat: provision_engineer_workspace activity (worktree off task branch)"
```

### Task 1.4: Parameterize `agent_step` workspace via `workspace_key`

`_run_instructed_agent` hardcodes `runs/{run_id}`. Add an optional `workspace_key` (default preserves today's behavior).

**Files:**
- Modify: `src/interactors/temporal/activities.py` (`_run_instructed_agent` ~line 364, `agent_step` ~line 513)
- Test: `tests/unit/test_orchestration_activities.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_orchestration_activities.py  (append; reuse _factory/_seed_run/_acts)
def test_agent_step_uses_custom_workspace_key(tmp_path):
    factory = _factory()
    _seed_run(factory)
    spy = _ResultSpy()  # captures ctx (defined earlier in this file)
    from adapters.storage.local import LocalStorageAdapter
    storage = LocalStorageAdapter(base_dir=str(tmp_path))
    acts = _acts(factory, runtime=spy, storage=storage)
    acts.agent_step({"run_id": "r1", "owner_id": "dev-user", "role": "backend",
                     "incoming": "do it", "task_title": "T", "acceptance_criteria": [],
                     "team_id": None, "workspace_key": "runs/r1/w/backend-1-0"})
    assert spy.ctx.workspace_path.endswith("runs/r1/w/backend-1-0")
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/unit/test_orchestration_activities.py::test_agent_step_uses_custom_workspace_key -q`
Expected: FAIL (workspace_path ends with `runs/r1`, not the custom key).

- [ ] **Step 3: Implement**

```python
# src/interactors/temporal/activities.py  — in _run_instructed_agent, replace:
#   workspace_path = self._storage.local_path(f"runs/{run_id}")
# with:
    workspace_key = payload.get("workspace_key") or f"runs/{run_id}"
    workspace_path = self._storage.local_path(workspace_key)
```
`agent_step` already passes `payload` through to `_run_instructed_agent`, so the key flows automatically. No other change needed.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_orchestration_activities.py -q`
Expected: PASS.

- [ ] **Step 5: Commit + open PR 1**

```bash
git add src/interactors/temporal/activities.py tests/unit/test_orchestration_activities.py
git commit -m "feat: agent_step accepts a workspace_key (defaults to runs/<run_id>)"
make coverage && uv run ruff check src tests
git push -u origin feat/parallel-eng-1
gh pr create --title "feat: parallel-engineers phase 1 — per-engineer worktree plumbing" --body "Additive enabling work for parallel engineers (spec docs/specs/2026-06-15-parallel-engineers-design.md). No behavior change; new git/activity/storage capabilities, unit-tested."
```

---

## Phase 2 — Instanced concurrent dispatch + integration (PR 2)

Wire the plumbing in: K concurrent engineers per wave on isolated branches, committed and merged into the task branch; `open_pr` opens based on commits-ahead. Conflict **blocks** for now (re-plan is Phase 3). This is where the unified per-engineer model goes live; N=1 keeps working (parity test).

### Task 2.1: `max_parallel_per_role` guard (pure domain)

**Files:**
- Modify: `src/domain/orchestration/core.py` (`OrchestrationLimits`, a new helper)
- Test: `tests/unit/test_orchestration.py` (holds the `guard_exceeded` / `OrchestrationLimits` tests)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_orchestration.py  (append)
from domain.orchestration import OrchestrationLimits, wave_exceeds_parallel

def test_wave_exceeds_parallel_per_role():
    limits = OrchestrationLimits(max_parallel_per_role=2)
    assert wave_exceeds_parallel(["backend", "backend"], limits) is False
    assert wave_exceeds_parallel(["backend", "backend", "backend"], limits) is True
    assert wave_exceeds_parallel(["backend", "qa"], limits) is False
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/unit/test_orchestration.py::test_wave_exceeds_parallel_per_role -q`
Expected: FAIL (ImportError: `wave_exceeds_parallel`).

- [ ] **Step 3: Implement**

```python
# src/domain/orchestration/core.py
# In OrchestrationLimits add:
    max_parallel_per_role: int = 3
    max_integration_rounds: int = 3

# New pure helper (module level):
def wave_exceeds_parallel(target_roles: list[str], limits: OrchestrationLimits) -> bool:
    """True if any single role is dispatched more than max_parallel_per_role times in one wave."""
    from collections import Counter
    counts = Counter(target_roles)
    return any(n > limits.max_parallel_per_role for n in counts.values())
```
Export `wave_exceeds_parallel` from `src/domain/orchestration/__init__.py` (add to its imports/`__all__`).

- [ ] **Step 4: Run tests; Step 5: Commit**

Run: `uv run pytest tests/unit/test_orchestration.py -q` → PASS
```bash
git add src/domain/orchestration tests/unit/test_orchestration.py
git commit -m "feat: max_parallel_per_role guard for engineer waves"
```

### Task 2.2: `integrate_branches` activity

**Files:**
- Modify: `src/interactors/temporal/activities.py`
- Test: `tests/unit/test_activities.py`

- [ ] **Step 1: Write the failing test (FakeGit, clean + conflict)**

```python
# tests/unit/test_activities.py  (append)
def test_integrate_branches_clean_and_conflict():
    factory = _factory(); run_id = _seed_run(factory)
    # clean: FakeGit merges both
    git = FakeGit()
    acts = _acts(factory, git=git)
    out = acts.integrate_branches({"run_id": run_id, "owner_id": "u1",
        "workspace_key": f"runs/{run_id}", "branches": ["agent/t__e0", "agent/t__e1"]})
    assert out["conflict"] is None and out["merged"] == ["agent/t__e0", "agent/t__e1"]
    # conflict on the 2nd branch
    git2 = FakeGit(merge_conflict_on=("agent/t__e1",))
    acts2 = _acts(factory, git=git2)
    out2 = acts2.integrate_branches({"run_id": run_id, "owner_id": "u1",
        "workspace_key": f"runs/{run_id}", "branches": ["agent/t__e0", "agent/t__e1"]})
    assert out2["merged"] == ["agent/t__e0"]
    assert out2["conflict"]["branch"] == "agent/t__e1"
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/unit/test_activities.py::test_integrate_branches_clean_and_conflict -q`
Expected: FAIL (no `integrate_branches`).

- [ ] **Step 3: Implement**

```python
# src/interactors/temporal/activities.py  (add near open_pr)
@activity.defn(name="integrate_branches")
def integrate_branches(self, payload: dict) -> dict:
    workspace = self._storage.local_path(payload["workspace_key"])
    merged: list[str] = []
    for branch in payload["branches"]:
        result = self._git.merge_branch(workspace, branch=branch)
        if not result.ok:
            self.record_event({"run_id": payload["run_id"], "owner_id": payload["owner_id"],
                               "stage": "implement", "type": "agent_reported",
                               "message": f"merge conflict on {branch}: {result.conflict_files}"})
            return {"merged": merged,
                    "conflict": {"branch": branch, "files": result.conflict_files}}
        merged.append(branch)
        self.record_event({"run_id": payload["run_id"], "owner_id": payload["owner_id"],
                           "stage": "implement", "type": "agent_reported",
                           "message": f"merged {branch}"})
    return {"merged": merged, "conflict": None}
```

- [ ] **Step 4: Run tests; Step 5: Commit**

Run: `uv run pytest tests/unit/test_activities.py -q` → PASS
```bash
git add src/interactors/temporal/activities.py tests/unit/test_activities.py
git commit -m "feat: integrate_branches activity (deterministic merge, conflict surfaced)"
```

### Task 2.3: `open_pr` opens on commits-ahead-of-base

**Files:**
- Modify: `src/interactors/temporal/activities.py` (`open_pr`)
- Test: `tests/unit/test_activities.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_activities.py  (append)
def test_open_pr_records_branch_when_ahead_without_worktree_changes():
    factory = _factory(); run_id = _seed_run(factory)
    git = FakeGit(has_changes=False, ahead=True)  # nothing uncommitted, but branch is ahead
    acts = _acts(factory, git=git)
    out = acts.open_pr({"run_id": run_id, "owner_id": "u1", "profile": "local",
                        "branch": "agent/t1", "base": "main", "title": "t", "body": "b"})
    assert out["outcome"] == "ok"
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        assert uow.runs.get(run_id).branch == "agent/t1"  # recorded despite no commit_all change
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/unit/test_activities.py::test_open_pr_records_branch_when_ahead_without_worktree_changes -q`
Expected: FAIL (today `open_pr` returns "no changes to PR" and records nothing).

- [ ] **Step 3: Implement — replace the `commit_all`/`if not committed` head of `open_pr`**

```python
# src/interactors/temporal/activities.py  — in open_pr, replace:
#   committed = self._git.commit_all(workspace, payload["title"], exclude=WORKSPACE_SCRATCH)
#   if not committed:
#       self.record_event(... "no changes to PR" ...); return {"outcome": "ok", "pr_url": None}
# with:
    self._git.commit_all(workspace, payload["title"], exclude=WORKSPACE_SCRATCH)  # any stragglers
    if not self._git.has_commits_ahead(workspace, payload["base"]):
        self.record_event({"run_id": run_id, "owner_id": owner_id, "stage": "pr",
                           "type": "stage_completed", "message": "no changes to PR"})
        return {"outcome": "ok", "pr_url": None}
```
The rest of `open_pr` (push/forge for remote, record branch for local) is unchanged.

- [ ] **Step 4: Run tests; Step 5: Commit**

Run: `uv run pytest tests/unit/test_activities.py -q` → PASS
```bash
git add src/interactors/temporal/activities.py tests/unit/test_activities.py
git commit -m "feat: open_pr proceeds on commits-ahead-of-base (integration commits the work)"
```

### Task 2.4: Concurrent instanced dispatch + commit + integrate in `OrchestratorWorkflow`

The core wiring. Replace the single-actor dispatch with: group dispatches by role → guard → per-instance provision + actor + brief → `gather` → commit each engineer branch → integrate → (conflict: block for now). `AgentWorkflow` input gains `workspace_key`; the engineer's `agent_step` payload carries it (already supported by Task 1.4 — but `AgentWorkflow` must pass it through).

**Files:**
- Modify: `src/interactors/temporal/workflows.py` (the `continue` dispatch block in `OrchestratorWorkflow.run`; `AgentWorkflow.run`'s `agent_step` call)
- Modify: `src/interactors/temporal/worker.py` (register `provision_engineer_workspace`, `integrate_branches` activities)
- Test: `tests/workflow/test_orchestrator_workflow.py`

- [ ] **Step 1: Write the failing test (two engineers, clean integrate → done)**

```python
# tests/workflow/test_orchestrator_workflow.py  (append)
def _two_engineer_lead(instr):
    if "wave 0" in instr:
        return {"intent": "continue", "dispatches": [
            {"target_role": "backend", "instructions": "build api"},
            {"target_role": "backend", "instructions": "build ui"}]}
    return {"intent": "verify"}

@pytest.mark.asyncio
async def test_orchestrator_runs_two_parallel_engineers_to_done():
    factory = _factory(); _seed(factory)
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with _worker(env, factory, lead=_two_engineer_lead):
            await env.client.execute_workflow(
                OrchestratorWorkflow.run, _input(AutonomyLevel.FULL_AUTO),
                id="r1", task_queue="t")
    assert _status(factory) == RunStatus.DONE
```
`_worker` (in this file) registers activities via `RunActivities`; add `acts.provision_engineer_workspace` and `acts.integrate_branches` to its `activities=[...]` list. The `_ScriptRuntime` already returns ok for worker steps, so both engineers "succeed"; `FakeGit` integrates cleanly.

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/workflow/test_orchestrator_workflow.py::test_orchestrator_runs_two_parallel_engineers_to_done -q`
Expected: FAIL — today only one `agent-r1-backend` actor is spawned (id collision / one brief), and there is no integration step.

- [ ] **Step 3: Implement — `AgentWorkflow` passes `workspace_key` to `agent_step`**

```python
# src/interactors/temporal/workflows.py  — in AgentWorkflow.run, the agent_step call:
result = await workflow.execute_activity(
    "agent_step",
    {"run_id": run_id, "owner_id": owner_id, "role": role,
     "incoming": msg.get("body", ""), "task_title": inp["task_title"],
     "acceptance_criteria": inp.get("acceptance_criteria", []),
     "team_id": inp.get("team_id"),
     "workspace_key": inp.get("workspace_key")},   # <-- added
    start_to_close_timeout=_STAGE_TIMEOUT, retry_policy=_RETRY)
```

- [ ] **Step 4: Implement — concurrent dispatch + commit + integrate**

Replace the `# intent == continue: dispatch a wave of actors` block in `OrchestratorWorkflow.run` (the part from `dispatches = decision.get("dispatches", [])` through the `QUIESCENCE_REACHED` event) with:

```python
            dispatches = decision.get("dispatches", [])
            target_roles = [d["target_role"] for d in dispatches]
            guard = guard_exceeded(state, limits)
            if guard or not dispatches or wave_exceeds_parallel(target_roles, limits):
                reason = guard or ("max_parallel_per_role"
                                   if dispatches else "no dispatches")
                await self._persist(run_id, owner_id, status=RunStatus.BLOCKED)
                await self._event(run_id, owner_id, "plan", RunEventType.BLOCKED, f"guard:{reason}")
                await self._cleanup(run_id, owner_id)
                return RunStatus.BLOCKED

            wave += 1
            await self._persist(run_id, owner_id, status=RunStatus.RUNNING,
                                stage=RunStage.IMPLEMENT)
            # provision an isolated worktree + spawn an actor per dispatch instance
            handles, eng_branches = [], []
            for i, d in enumerate(dispatches):
                role = d["target_role"]
                inst_branch = f"{branch}__{role}-{wave}-{i}"
                ws_key = f"runs/{run_id}/w/{role}-{wave}-{i}"
                await workflow.execute_activity(
                    "provision_engineer_workspace",
                    {"run_id": run_id, "owner_id": owner_id, "profile": inp["profile"],
                     "repo_ref": inp["repo_ref"], "base": branch,
                     "branch": inst_branch, "workspace_key": ws_key},
                    start_to_close_timeout=_STAGE_TIMEOUT, retry_policy=_RETRY)
                await self._event(run_id, owner_id, "implement",
                                  RunEventType.AGENT_DISPATCHED, f"dispatch {role} #{i}")
                child = await workflow.start_child_workflow(
                    AgentWorkflow.run,
                    {"run_id": run_id, "owner_id": owner_id, "role": role,
                     "agent_id": role_to_agent_id.get(role, role),
                     "parent_workflow_id": workflow.info().workflow_id,
                     "task_title": inp["task_title"],
                     "acceptance_criteria": inp.get("acceptance_criteria", []),
                     "team_id": inp.get("team_id"), "role_to_agent_id": role_to_agent_id,
                     "project_id": inp.get("project_id"), "work_item_id": inp.get("task_id"),
                     "workspace_key": ws_key},
                    id=f"agent-{run_id}-{role}-{wave}-{i}")
                await child.signal("deliver", {"body": d["instructions"]})
                await child.signal("stop_now")
                handles.append((role, child))
                eng_branches.append((ws_key, inst_branch))
            results = await asyncio.gather(*[h for _, h in handles])
            wave_cost = sum(float(r.get("cost_usd", 0.0)) for r in results)
            cost += wave_cost
            await self._persist(run_id, owner_id, cost_usd=cost)
            state = state.record_wave(dispatch_count=len(dispatches),
                                      messages=len(dispatches), cost=wave_cost)
            for (role, _), r in zip(handles, results):
                state = state.record_report(
                    AgentReport(role=AgentRole(role),
                                outcome=AgentOutcome(r.get("outcome", "ok")),
                                cost_usd=float(r.get("cost_usd", 0.0))))
            # commit each engineer's work to its branch, then integrate into the task branch
            committed_branches = []
            for ws_key, inst_branch in eng_branches:
                ok = await workflow.execute_activity(
                    "commit_engineer_branch",
                    {"run_id": run_id, "owner_id": owner_id, "workspace_key": ws_key,
                     "title": inp["task_title"]},
                    start_to_close_timeout=_STAGE_TIMEOUT, retry_policy=_RETRY)
                if ok:
                    committed_branches.append(inst_branch)
            integ = await workflow.execute_activity(
                "integrate_branches",
                {"run_id": run_id, "owner_id": owner_id,
                 "workspace_key": f"runs/{run_id}", "branches": committed_branches},
                start_to_close_timeout=_STAGE_TIMEOUT, retry_policy=_RETRY)
            if integ["conflict"] is not None:
                # Phase 2: block on conflict. Phase 3 replaces this with a lead re-plan.
                await self._persist(run_id, owner_id, status=RunStatus.BLOCKED)
                await self._event(run_id, owner_id, "implement", RunEventType.BLOCKED,
                                  f"merge conflict on {integ['conflict']['branch']}")
                await self._cleanup(run_id, owner_id)
                return RunStatus.BLOCKED
            await self._event(run_id, owner_id, "implement", RunEventType.QUIESCENCE_REACHED,
                              f"wave {wave} complete")
```

- [ ] **Step 5: Implement — `commit_engineer_branch` activity**

```python
# src/interactors/temporal/activities.py  (add near integrate_branches)
@activity.defn(name="commit_engineer_branch")
def commit_engineer_branch(self, payload: dict) -> bool:
    workspace = self._storage.local_path(payload["workspace_key"])
    return self._git.commit_all(workspace, payload["title"], exclude=WORKSPACE_SCRATCH)
```
Register `commit_engineer_branch`, `provision_engineer_workspace`, `integrate_branches` in
`src/interactors/temporal/worker.py`'s activity list.

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/workflow/ tests/unit/test_activities.py -q`
Expected: PASS, including the existing single-engineer tests (N=1 parity — they now go through provision_engineer_workspace + integrate as a fast-forward; FakeGit integrates cleanly).

- [ ] **Step 7: Commit + open PR 2**

```bash
git add src/interactors/temporal tests/
git commit -m "feat: concurrent instanced engineer dispatch + per-branch commit + integrate"
make coverage && uv run ruff check src tests
git push -u origin feat/parallel-eng-2
gh pr create --title "feat: parallel-engineers phase 2 — concurrent dispatch + integration" --body "K engineers per wave on isolated worktrees, merged into the task branch; conflict blocks (re-plan in phase 3). Spec docs/specs/2026-06-15-parallel-engineers-design.md."
```

---

## Phase 3 — Conflict → lead re-plan (PR 3)

Make conflicts recoverable: surface the conflict to the lead via `OrchestrationState.last_integration` + prompt, replace the Phase-2 block with a bounded re-plan loop.

### Task 3.1: `OrchestrationState.last_integration` + prompt section

**Files:**
- Modify: `src/domain/orchestration/core.py` (`OrchestrationState` field + a recorder)
- Modify: `src/domain/orchestration/prompts.py` (`build_orchestrator_prompt`)
- Test: `tests/unit/test_orchestration.py` (state), `tests/unit/test_orchestration_prompts.py` (prompt)

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_orchestration.py  (append)
def test_record_integration_sets_last_integration():
    from domain.orchestration import OrchestrationState
    s = OrchestrationState().record_integration({"branch": "agent/t__e1", "files": ["a.py"]})
    assert s.last_integration["branch"] == "agent/t__e1"

# tests/unit/test_orchestration_prompts.py  (append)
def test_prompt_includes_integration_conflict():
    from domain.orchestration import OrchestrationState, build_orchestrator_prompt
    from domain.models import AgentRole
    s = OrchestrationState().record_integration({"branch": "agent/t__e1", "files": ["a.py"]})
    p = build_orchestrator_prompt(task_title="T", acceptance_criteria=[], body="",
                                  state=s, available_roles=[AgentRole.BACKEND])
    assert "a.py" in p and "conflict" in p.lower()
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/unit/test_orchestration.py::test_record_integration_sets_last_integration tests/unit/test_orchestration_prompts.py::test_prompt_includes_integration_conflict -q`
Expected: FAIL (no `record_integration` / no conflict text).

- [ ] **Step 3: Implement — state**

```python
# src/domain/orchestration/core.py  — in OrchestrationState add field + method:
    last_integration: dict | None = None

    def record_integration(self, conflict: dict | None) -> "OrchestrationState":
        return self.model_copy(update={"last_integration": conflict})
```

- [ ] **Step 4: Implement — prompt**

```python
# src/domain/orchestration/prompts.py  — in build_orchestrator_prompt, build a section:
    integration = ""
    if state.last_integration:
        files = ", ".join(state.last_integration.get("files", [])) or "(unknown files)"
        integration = (
            "\n\nIntegration conflict — the branch "
            f"{state.last_integration.get('branch', '?')} could not be merged (conflicting "
            f"files: {files}). Re-dispatch one engineer to resolve it against the integrated "
            "base, then verify."
        )
# ...and append `{integration}` into the returned prompt string (next to `{feedback}`).
```

- [ ] **Step 5: Run tests; Step 6: Commit**

Run the two test files → PASS.
```bash
git add src/domain/orchestration tests/unit/test_orchestration.py tests/unit/test_orchestration_prompts.py
git commit -m "feat: surface integration conflicts to the lead (state + prompt)"
```

### Task 3.2: Replace the Phase-2 conflict block with a bounded re-plan

**Files:**
- Modify: `src/interactors/temporal/workflows.py` (`OrchestratorWorkflow.run`: the `if integ["conflict"]` branch + a `integration_rounds` counter)
- Test: `tests/workflow/test_orchestrator_workflow.py`

- [ ] **Step 1: Write the failing tests (re-plan→done, and exhaust→blocked)**

```python
# tests/workflow/test_orchestrator_workflow.py  (append)
def _conflict_then_fix_lead():
    seen = {"n": 0}
    def lead(instr):
        if "wave 0" in instr:
            return {"intent": "continue", "dispatches": [
                {"target_role": "backend", "instructions": "api"},
                {"target_role": "backend", "instructions": "ui"}]}
        if "Integration conflict" in instr and seen["n"] == 0:
            seen["n"] = 1
            return {"intent": "continue",
                    "dispatches": [{"target_role": "backend", "instructions": "resolve"}]}
        return {"intent": "verify"}
    return lead

@pytest.mark.asyncio
async def test_orchestrator_replans_on_merge_conflict_then_done():
    factory = _factory(); _seed(factory)
    # FakeGit conflicts only on the first wave's 2nd branch
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with _worker(env, factory, lead=_conflict_then_fix_lead(),
                           merge_conflict_on=("agent/t1__backend-1-1",)):
            await env.client.execute_workflow(
                OrchestratorWorkflow.run, _input(AutonomyLevel.FULL_AUTO),
                id="r1", task_queue="t")
    assert _status(factory) == RunStatus.DONE
```
Extend `_worker` in this file to accept `merge_conflict_on=()` and pass it to `FakeGit(merge_conflict_on=...)`. (The branch id `agent/t1__backend-1-1` follows `{branch}__{role}-{wave}-{i}` with `branch=agent/<task_id>`; confirm the seeded task id yields `agent/t1` — adjust the literal to the seeded id.)

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/workflow/test_orchestrator_workflow.py::test_orchestrator_replans_on_merge_conflict_then_done -q`
Expected: FAIL — Phase 2 blocks on conflict instead of re-planning.

- [ ] **Step 3: Implement — counter + re-plan**

Initialize near the top of `run` (next to `verify_rounds = 0`): `integration_rounds = 0`.
Replace the Phase-2 conflict block with:

```python
            if integ["conflict"] is not None:
                integration_rounds += 1
                state = state.record_integration(integ["conflict"])
                if integration_rounds >= limits.max_integration_rounds:
                    await self._persist(run_id, owner_id, status=RunStatus.BLOCKED)
                    await self._event(run_id, owner_id, "implement", RunEventType.BLOCKED,
                                      f"unresolved merge conflict on {integ['conflict']['branch']}")
                    await self._cleanup(run_id, owner_id)
                    return RunStatus.BLOCKED
                await self._event(run_id, owner_id, "implement", RunEventType.QUIESCENCE_REACHED,
                                  f"wave {wave} conflict -> re-plan")
                continue  # back to invoke_lead, which now sees last_integration
            state = state.record_integration(None)  # clean wave clears prior conflict
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/workflow/ -q`
Expected: PASS (re-plan→done; and add/confirm an exhaust→blocked test by setting the lead to keep conflicting).

- [ ] **Step 5: Commit + open PR 3**

```bash
git add src/interactors/temporal/workflows.py tests/workflow/test_orchestrator_workflow.py
git commit -m "feat: merge conflict becomes a bounded lead re-plan"
make coverage && uv run ruff check src tests
git push -u origin feat/parallel-eng-3
gh pr create --title "feat: parallel-engineers phase 3 — conflict re-plan loop" --body "Merge conflicts surface to the lead (state+prompt) and become a bounded re-plan; max_integration_rounds blocks. Completes spec docs/specs/2026-06-15-parallel-engineers-design.md."
```

---

## Final validation (after Phase 3)

- [ ] `make coverage` ≥ 80% and `uv run ruff check src tests` clean on each PR.
- [ ] Fake-e2e: two disjoint engineers → done; two conflicting → re-plan → done; conflict exhausts → blocked; `max_parallel_per_role` exceeded → blocked; **N=1 parity** → done + committed `agent/<task>`.
- [ ] Optional real run (local profile, existing Claude CLI auth) with a ticket the lead is likely to split, confirming two engineer branches merge into `agent/<task>` (mirrors the orchestrator-cutover validation runbook in `docs/plans/2026-06-13-yaah-e2e-local-validation.md`).

## Notes / deferred (from the spec)

- **Workspace cleanup** is inherited from the existing `cleanup_workspace` activity, which
  `delete_directory("runs/{run_id}/")` — this rmtrees the engineer worktrees under
  `runs/{run_id}/w/*` along with the main one. The git worktree *registry* entries in the repo
  may go stale; add a best-effort `git worktree prune` (cwd=repo_ref) at the start of
  `provision_engineer_workspace` to keep it tidy. Not load-bearing for local runs.
- **Provision idempotency:** `git worktree add -b <branch>` fails if the branch/worktree already
  exists, which a Temporal activity *retry* (not replay) could hit after a partial failure. If
  flakiness appears, make `provision_engineer_workspace` defensive: `git worktree prune` then
  remove a pre-existing `<branch>`/worktree before `prepare`. Deferred until observed (the
  existing `provision_workspace` has the same property and has been stable).
- Live engineer↔engineer messaging, a persistent actor pool, and AI-assisted conflict resolution remain out of scope.
- A board-UI surface for parallel engineers (multiple active-now assignee chips, per-instance output) is a separate later spec on top of the agent-visibility UI.
