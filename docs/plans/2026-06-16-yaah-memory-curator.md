# Project-Memory Curator (Revive) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-introduce the dropped project-memory curator: at the end of a successful run, a generic LEARN-stage agent updates `CLAUDE.md`/`AGENTS.md`/`docs/adr`, captured via the existing A6b `MemoryProposal` apply/reject flow — inserted **after** `open_pr` so it never pollutes the work PR.

**Architecture:** A new `curate_memory` activity runs `_run_instructed_agent(role=None, stage=LEARN)` in the main run worktree, best-effort. `OrchestratorWorkflow` calls it between `open_pr` and `capture_memory` on the success path. The `for_stage(LEARN)` prompt is enriched with the run's task context. Everything downstream (`capture_memory`, `MemoryProposal`, board card, apply/reject, `full_auto`) is reused unchanged.

**Tech Stack:** Python 3.12, `uv`, Temporal (`temporalio`), Pydantic v2, pytest. Spec: `docs/specs/2026-06-16-memory-curator-design.md`.

**Conventions (read before starting):**
- Tests: `uv run pytest <path> -q`. Gate: `make coverage` (80%) + `uv run ruff check src tests` (lines ≤100, no `;`).
- Domain pure (no I/O). Activities are the only DB/FS writers. Workflows deterministic.
- Each phase = one PR off the latest `main`, in a git worktree. Commit per task.

---

## Phase 1 — Curator prompt + activity (PR 1)

Additive: enrich the LEARN prompt and add the `curate_memory` activity. Not yet wired into the workflow; behavior unchanged.

### Task 1.1: Enrich `for_stage(LEARN)` with the run's task context

**Files:**
- Modify: `src/domain/agent/prompts.py` (the `RunStage.LEARN` branch of `for_stage`)
- Test: `tests/unit/test_prompts.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_prompts.py  (append)
def test_for_stage_learn_includes_task_context():
    from domain.agent.prompts import for_stage
    from domain.models import RunStage
    prompt, tools = for_stage(RunStage.LEARN, "Add OAuth login",
                              ["users can log in with Google"], body="see ticket")
    assert "project memory" in prompt.lower()              # the durable-learnings guidance
    assert tools == ["Read", "Edit", "Write"]              # surgical-edit tools
    assert "Add OAuth login" in prompt                     # the run's ticket
    assert "users can log in with Google" in prompt        # acceptance context
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/unit/test_prompts.py::test_for_stage_learn_includes_task_context -q`
Expected: FAIL (the LEARN branch ignores `task_title`/`acceptance_criteria`).

- [ ] **Step 3: Implement** — in `src/domain/agent/prompts.py`, replace the `RunStage.LEARN` branch's return. The function already binds `ac = "\n".join(f"- {c}" for c in acceptance_criteria)` on its first line (used by the other stage branches); reuse `ac`:

```python
    if stage == RunStage.LEARN:
        return (
            "Update project memory with durable learnings from this run. Edit CLAUDE.md "
            "or AGENTS.md at the repo root (keep each concise, ~120 lines max) and add or "
            "update entries under docs/adr/ for architectural decisions. Propose additions "
            "AND deletions: remove stale or wrong guidance, record new conventions and "
            "gotchas. Only durable, project-wide knowledge belongs here.\n\n"
            f"This run completed the ticket: {task_title}\n{body}\n\nAcceptance criteria:\n{ac}\n"
            "Record only durable, project-wide learnings — not this task's specifics.",
            ["Read", "Edit", "Write"],
        )
```
(If `ac` is not already bound at the top of `for_stage`, add `ac = "\n".join(f"- {c}" for c in acceptance_criteria)` at the function start, matching the other branches.)

- [ ] **Step 4: Run** `uv run pytest tests/unit/test_prompts.py -q` → PASS. (If an existing test asserted the *exact* old LEARN string, update it to the new prefix.) `uv run ruff check src/domain/agent/prompts.py tests/unit/test_prompts.py`.

- [ ] **Step 5: Commit**

```bash
git add src/domain/agent/prompts.py tests/unit/test_prompts.py
git commit -m "feat: for_stage(LEARN) carries the run's task context for the curator"
```

### Task 1.2: `curate_memory` activity + worker registration

**Files:**
- Modify: `src/interactors/temporal/activities.py` (new `curate_memory` activity)
- Modify: `src/interactors/temporal/worker.py` (register it)
- Test: `tests/unit/test_orchestration_activities.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_orchestration_activities.py  (append; reuse _factory/_seed_run/_acts/_ResultSpy)
def test_curate_memory_runs_learn_agent_in_main_workspace(tmp_path):
    from adapters.storage.local import LocalStorageAdapter
    factory = _factory()
    _seed_run(factory)
    spy = _ResultSpy()
    acts = _acts(factory, runtime=spy, storage=LocalStorageAdapter(base_dir=str(tmp_path)))
    acts.curate_memory({"run_id": "r1", "owner_id": "dev-user", "task_title": "Add OAuth",
                        "acceptance_criteria": ["login works"], "body": ""})
    from domain.models import RunStage
    assert spy.ctx.stage == RunStage.LEARN
    assert spy.ctx.workspace_path.endswith("runs/r1")          # main worktree, not an instance
    assert "project memory" in spy.ctx.instructions.lower()    # LEARN prompt reached the agent
    assert "Add OAuth" in spy.ctx.instructions                 # task context


def test_curate_memory_swallows_agent_failure(tmp_path):
    from adapters.storage.local import LocalStorageAdapter
    factory = _factory()
    _seed_run(factory)

    class _Boom:
        def run_stage(self, ctx):
            raise RuntimeError("curation blew up")
            yield  # pragma: no cover - make it a generator
        def cancel(self, run_id): ...

    acts = _acts(factory, runtime=_Boom(), storage=LocalStorageAdapter(base_dir=str(tmp_path)))
    out = acts.curate_memory({"run_id": "r1", "owner_id": "dev-user", "task_title": "T",
                              "acceptance_criteria": [], "body": ""})
    assert out["outcome"] == "ok"   # advisory: a curator failure never fails the run
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/unit/test_orchestration_activities.py -k curate_memory -q`
Expected: FAIL (`AttributeError: ... no attribute 'curate_memory'`).

- [ ] **Step 3: Implement the activity** (`src/interactors/temporal/activities.py`, place near `capture_memory`):

```python
@activity.defn(name="curate_memory")
def curate_memory(self, payload: dict) -> dict:
    """Run the LEARN curator (generic role -> Read/Edit/Write) in the main run worktree to
    update project memory. Advisory: a curator failure never fails the run."""
    from domain.agent.prompts import for_stage
    from domain.models import RunStage
    learn_prompt, _tools = for_stage(
        RunStage.LEARN, payload["task_title"],
        payload.get("acceptance_criteria", []), payload.get("body", ""))
    try:
        self._run_instructed_agent(
            payload, role=None, instructions=learn_prompt, stage=RunStage.LEARN)
    except Exception:  # noqa: BLE001 - curation is advisory; never fail the run
        pass
    return {"outcome": "ok"}
```
(`_run_instructed_agent(payload, role=None, ...)` resolves the workspace as `payload.get("workspace_key") or f"runs/{run_id}"` → the main worktree, and with `role=None` builds no manifest, so `build_invocation` falls back to `for_stage(LEARN)`'s `Read/Edit/Write` tools. The bare `except` keeps curation best-effort — a failed curator yields an empty memory diff, and `capture_memory` records "no memory changes" as before.)

- [ ] **Step 4: Register in the worker** (`src/interactors/temporal/worker.py`): add `acts.curate_memory` to the list returned by `build_activities` (next to `acts.capture_memory`):

```python
    return [acts.persist_run_state, acts.record_event, acts.record_usage,
            acts.cleanup_workspace, acts.provision_workspace, acts.open_pr,
            acts.record_notification, acts.capture_memory, acts.curate_memory,
            # ... keep the remaining existing entries unchanged ...
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/unit/test_orchestration_activities.py tests/unit/test_worker_build.py -q`
Expected: PASS — but first update `tests/unit/test_worker_build.py::test_build_activities_returns_all_registered`, whose `assert len(acts) == 15` must become `assert len(acts) == 16` now that `curate_memory` is registered.

- [ ] **Step 6: Commit + open PR 1**

```bash
git add src/interactors/temporal tests/unit/test_orchestration_activities.py tests/unit/test_worker_build.py
git commit -m "feat: curate_memory activity (generic LEARN agent, best-effort)"
make coverage && uv run ruff check src tests
git push -u origin feat/memory-curator-1
gh pr create --title "feat: memory curator phase 1 — LEARN prompt + curate_memory activity" --body "Phase 1 of reviving the project-memory curator (spec docs/specs/2026-06-16-memory-curator-design.md): enrich for_stage(LEARN) with task context; add the curate_memory activity + worker registration. Additive; not yet wired into the workflow."
```

---

## Phase 2 — Wire into the orchestrator (PR 2)

Insert `curate_memory` between `open_pr` and `capture_memory` on the success path.

### Task 2.1a: Test infra — record stages run + register `curate_memory`

The fake-e2e tests must *prove the curator ran*, not just that a proposal exists (with `FakeGit`, `capture_memory` produces a proposal from the faked diff regardless of curation). The deterministic signal: the curator is the only step whose `ctx.stage == RunStage.LEARN`. Make `_ScriptRuntime` record stages and expose the list, and register the new activity in the test worker.

**Files:**
- Modify: `tests/workflow/test_orchestrator_workflow.py` (`_ScriptRuntime`, `_worker`)

- [ ] **Step 1: Record stages in `_ScriptRuntime`** — add a `stages_seen` param and append each stage:

```python
    def __init__(self, storage=None, lead=_default_lead, monitor=None,
                 worker_outcome="ok", cost=0.0, stages_seen=None):
        self._storage = storage
        self._lead = lead
        self._monitor = monitor or (lambda instr: {"complete": True})
        self._worker_outcome = worker_outcome
        self._cost = cost
        self._stages_seen = stages_seen if stages_seen is not None else []

    def run_stage(self, ctx):
        self._stages_seen.append(ctx.stage)
        instr = ctx.instructions or ""
        # ... rest unchanged ...
```

- [ ] **Step 2: Thread it through `_worker`** — add a `stages_seen=None` param, pass it to `_ScriptRuntime`, and register `acts.curate_memory` in the activities list:

```python
def _worker(env, factory, lead=_default_lead, monitor=None, worker_outcome="ok", cost=0.0,
            git=None, stages_seen=None):
    storage = LocalStorageAdapter(base_dir=tempfile.mkdtemp())
    acts = RunActivities(
        factory, _ScriptRuntime(storage, lead, monitor, worker_outcome, cost, stages_seen),
        storage, git or FakeGit(), FakeGitForge())
    return Worker(
        env.client, task_queue="t",
        workflows=[OrchestratorWorkflow, AgentWorkflow],
        activities=[acts.provision_workspace, acts.invoke_lead, acts.agent_step,
                    acts.run_monitor, acts.persist_messages, acts.persist_run_state,
                    acts.record_event, acts.record_usage, acts.open_pr,
                    acts.capture_memory, acts.curate_memory, acts.cleanup_workspace,
                    acts.provision_engineer_workspace, acts.integrate_branches,
                    acts.commit_engineer_branch],
        activity_executor=ThreadPoolExecutor(max_workers=4))
```

- [ ] **Step 3: Run** `uv run pytest tests/workflow/test_orchestrator_workflow.py -q` → PASS (pure refactor; existing tests still green, `curate_memory` is registered but not yet called by the workflow).

### Task 2.1b: Insert `curate_memory` in `OrchestratorWorkflow`

**Files:**
- Modify: `src/interactors/temporal/workflows.py` (between the unconditional `open_pr` and `capture_memory` activity calls on the success path — these run *after* the `if RunStage.PR in gates:` block, not inside it)
- Test: `tests/workflow/test_orchestrator_workflow.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/workflow/test_orchestrator_workflow.py  (append; RunStage is imported from domain.models)
@pytest.mark.asyncio
async def test_orchestrator_curates_and_captures_proposal_on_success():
    factory = _factory()
    _seed(factory)
    stages = []
    git = FakeGit(memory_diff="--- a/CLAUDE.md\n+++ b/CLAUDE.md\n+learned: pin deps\n")
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with _worker(env, factory, git=git, stages_seen=stages):
            await env.client.execute_workflow(
                OrchestratorWorkflow.run, _input(AutonomyLevel.FULL_AUTO),
                id="r1", task_queue="t")
    assert _status(factory) == RunStatus.DONE
    assert RunStage.LEARN in stages                 # the curator agent actually ran
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        proposals = uow.memory_proposals.list(filters={"run_id": "r1"}).results
    assert len(proposals) == 1                       # its edits became one MemoryProposal


@pytest.mark.asyncio
async def test_orchestrator_curation_noop_makes_no_proposal():
    factory = _factory()
    _seed(factory)
    stages = []
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with _worker(env, factory, stages_seen=stages):   # default FakeGit -> empty diff
            await env.client.execute_workflow(
                OrchestratorWorkflow.run, _input(AutonomyLevel.FULL_AUTO),
                id="r1", task_queue="t")
    assert _status(factory) == RunStatus.DONE
    assert RunStage.LEARN in stages                 # curator still ran...
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        proposals = uow.memory_proposals.list(filters={"run_id": "r1"}).results
    assert proposals == []                           # ...but a no-op diff makes no proposal


@pytest.mark.asyncio
async def test_orchestrator_blocked_run_never_curates():
    factory = _factory()
    _seed(factory)
    stages = []
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with _worker(env, factory, lead=_block_lead, stages_seen=stages):
            await env.client.execute_workflow(
                OrchestratorWorkflow.run, _input(AutonomyLevel.FULL_AUTO),
                id="r1", task_queue="t")
    assert _status(factory) == RunStatus.BLOCKED
    assert RunStage.LEARN not in stages             # blocked runs return before curation
```
(`_block_lead`, `_status`, `_seed`, `_input`, `FakeGit` all already exist in this file. `RunStage`/`RunStatus`/`AutonomyLevel` are imported at the top.)

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/workflow/test_orchestrator_workflow.py -k "curates or curation or never_curates" -q`
Expected: FAIL — `test_orchestrator_curates_and_captures_proposal_on_success` and `..._curation_noop...` fail on `RunStage.LEARN in stages` (the workflow never calls `curate_memory` yet). `..._never_curates` already passes.

- [ ] **Step 3: Implement** — in `src/interactors/temporal/workflows.py`, between the `open_pr` `execute_activity` call and the `capture_memory` `execute_activity` call (both at the same indentation, after the `if RunStage.PR in gates:` block), insert:

```python
        await workflow.execute_activity(
            "curate_memory",
            {"run_id": run_id, "owner_id": owner_id, "task_title": inp["task_title"],
             "acceptance_criteria": inp.get("acceptance_criteria", []),
             "body": inp.get("body", "")},
            start_to_close_timeout=_STAGE_TIMEOUT, retry_policy=_RETRY)
```
(Leave `open_pr` before it and `capture_memory` after it unchanged — order is `open_pr → curate_memory → capture_memory`.)

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/workflow/ tests/unit -q`
Expected: PASS (the three new tests + all existing orchestrator/agent tests).

- [ ] **Step 5: Commit**

```bash
git add src/interactors/temporal/workflows.py tests/workflow/test_orchestrator_workflow.py
git commit -m "feat: orchestrator curates memory between open_pr and capture_memory"
```

### Task 2.2: Real-git no-leakage proof

Pin decision #1: committing the work first, then editing a memory file, then committing only the memory paths to a separate branch keeps the memory edit OUT of the work branch.

**Files:**
- Test: `tests/unit/test_local_git.py`

- [ ] **Step 1: Write the failing test** (it should PASS once written — it exercises existing `LocalGit` methods to *document/guard* the ordering guarantee; if it fails, the ordering assumption is wrong and Phase 2 is unsafe). Mirrors the existing `test_commit_to_branch_commits_only_memory_paths`, reusing this file's `_init_repo(ws)` helper (`subprocess`/`tempfile`/`Path` are already imported):

```python
# tests/unit/test_local_git.py  (append)
def test_curate_after_pr_keeps_memory_out_of_work_branch():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        _init_repo(ws)                                   # repo on main with an initial commit
        # seed a tracked CLAUDE.md (so the curator's change is a modify, like a real repo)
        (ws / "CLAUDE.md").write_text("# Project\n")
        subprocess.run(["git", "-C", str(ws), "add", "CLAUDE.md"], check=True,
                       capture_output=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(ws),
                        "commit", "-m", "add project memory"], check=True, capture_output=True)
        git = LocalGit()
        # 1) open_pr: the agent's work is committed to the task branch
        subprocess.run(["git", "-C", str(ws), "checkout", "-b", "agent/t1"], check=True,
                       capture_output=True)
        (ws / "feature.py").write_text("print('hi')\n")
        assert git.commit_all(str(ws), "work") is True
        # 2) curator edits project memory AFTER the work commit (uncommitted working tree)
        (ws / "CLAUDE.md").write_text("# Project\n- learned: pin deps\n")
        # 3) capture_memory: commit ONLY the memory paths to a separate branch off the work branch
        assert git.commit_to_branch(str(ws), branch="agent/memory-r1", base="agent/t1",
                                    paths=["CLAUDE.md", "AGENTS.md", "docs/adr"],
                                    message="memory update") is True
        # work branch (agent/t1) has the work but NOT the curator's CLAUDE.md edit
        work_claude = subprocess.run(["git", "-C", str(ws), "show", "agent/t1:CLAUDE.md"],
                                     capture_output=True, text=True).stdout
        assert "learned: pin deps" not in work_claude
        work_files = subprocess.run(["git", "-C", str(ws), "ls-tree", "-r", "--name-only",
                                     "agent/t1"], capture_output=True, text=True).stdout
        assert "feature.py" in work_files
        # memory branch HAS the curator's edit
        mem_claude = subprocess.run(["git", "-C", str(ws), "show", "agent/memory-r1:CLAUDE.md"],
                                    capture_output=True, text=True).stdout
        assert "learned: pin deps" in mem_claude
```

- [ ] **Step 2: Run** `uv run pytest tests/unit/test_local_git.py::test_curate_after_pr_keeps_memory_out_of_work_branch -q` → PASS (proves the ordering guarantee with real git). If it FAILS, stop and report — the curate-after-PR assumption is broken.

- [ ] **Step 3: Commit + open PR 2**

```bash
git add tests/unit/test_local_git.py
git commit -m "test: prove curate-after-PR keeps memory edits out of the work branch"
make coverage && uv run ruff check src tests
git push -u origin feat/memory-curator-2
gh pr create --title "feat: memory curator phase 2 — wire into orchestrator + no-leakage proof" --body "Phase 2: insert curate_memory between open_pr and capture_memory on the success path; real-git test proves the curator's CLAUDE.md edits land only on the memory branch, not the work PR. Completes spec docs/specs/2026-06-16-memory-curator-design.md."
```

---

## Final validation (after Phase 2)

- [ ] `make coverage` ≥ 80% and `uv run ruff check src tests` clean on each PR.
- [ ] Fake-e2e: a successful run with a curator memory diff → exactly one `MemoryProposal`; a no-op curator → "no memory changes"; a blocked run never calls `curate_memory`.
- [ ] Real-git: the no-leakage test (memory edits on the memory branch, not the work branch).
- [ ] (Optional) real Claude run on a ticket worth a learning, confirming the curator updates `CLAUDE.md`/`docs/adr` → a `MemoryProposal` appears (visible on the board / `GET` memory-proposals) and applies under `full_auto` — mirrors the role-memory validation.

## Notes / deferred (from the spec)

- A "only propose if meaningfully changed" guard, and skipping curation for trivial tickets, are deferred.
- Role memory (DB-backed, already shipped) and Episodic (`progress.md`) memory are out of scope.
