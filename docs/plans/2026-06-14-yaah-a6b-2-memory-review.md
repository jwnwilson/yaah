# A6b-2 Memory-Diff Review & Apply — Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax. TDD per task; run the suite per wave; frequent commits.

**Goal:** Review proposed memory diffs and apply/reject them from the board; auto-apply in `full_auto`.

**Architecture:** Local apply = fast-forward base to `agent/memory-<run>`; remote apply = open a PR. A `MemoryApplier` interactor holds that branch and is shared by the apply endpoints and `capture_memory`'s auto path. `MemoryProposal` gains `pr_url`/`resolved_at`. UI adds a proposal card to the run section.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, Temporal, pytest; React + Vite + TS + vitest. `uv run` for backend.

**Source of truth:** `docs/specs/2026-06-14-a6b-2-memory-review-design.md`.

---

## Wave 1

### Task 1 (Lane G): `GitPort.merge_into_base` + FakeGit

**Files:** `src/adapters/git/ports.py`, `src/adapters/git/local_git.py`, `src/adapters/git/fake.py`; tests `tests/unit/test_fake_git.py`, `tests/unit/test_local_git.py`.

- [ ] Test (fake): `FakeGit(merge_ok=True).merge_into_base("/r", branch="agent/memory-x", base="main")` returns `True` and records `("/r","agent/memory-x","main")` in `git.merged_into_base`; default `FakeGit()` returns `True`.
- [ ] Test (local, real git tmp repo): create repo on `main`, commit `CLAUDE.md`; create `agent/memory-x` off main with an extra commit; `LocalGit().merge_into_base(repo, branch="agent/memory-x", base="main")` returns `True` and `main` now contains the extra commit (`git log main` includes it). Second test: when nothing to do (branch == base) returns `True` and base unchanged.
- [ ] Protocol: add to `GitPort`:
  ```python
  def merge_into_base(
      self, repo_ref: str, *, branch: str, base: str, token: str | None = None
  ) -> bool: ...
  ```
- [ ] FakeGit: add `merge_ok: bool = True` ctor param + `self.merged_into_base: list[tuple] = []`; method appends `(repo_ref, branch, base)` and returns `merge_ok`.
- [ ] LocalGit:
  ```python
  def merge_into_base(self, repo_ref, *, branch, base, token=None) -> bool:
      # Fast-forward base to branch when branch is a descendant of base.
      base_sha = self._run(["rev-parse", base], cwd=repo_ref).strip()
      branch_sha = self._run(["rev-parse", branch], cwd=repo_ref).strip()
      if base_sha == branch_sha:
          return True
      merge_base = self._run(["merge-base", base, branch], cwd=repo_ref).strip()
      if merge_base != base_sha:
          raise GitError(f"{base} has diverged from {branch}; manual merge required")
      # ff: point base ref at branch tip (base may be checked out elsewhere; ref update is safe ff)
      self._run(["update-ref", f"refs/heads/{base}", branch_sha, base_sha], cwd=repo_ref)
      return True
  ```
- [ ] Commit: `feat: GitPort.merge_into_base (fast-forward base to a branch)`.

### Task 2 (Lane M): `MemoryProposal` pr_url/resolved_at + ORM + migration

**Files:** `src/domain/models.py`, `src/adapters/database/orm.py`, migration; tests `tests/unit/test_memory_proposal_model.py`, `tests/unit/test_memory_proposal_repository.py`, `tests/unit/test_migrations.py`.

- [ ] Test (model): `MemoryProposal(...)` defaults `pr_url is None` and `resolved_at is None`; can be constructed with both set.
- [ ] Test (repo): round-trip a proposal with `pr_url="http://pr/1"`, `resolved_at=utc_now()`; fetched values match.
- [ ] Model: add to `MemoryProposal`:
  ```python
  pr_url: str | None = None
  resolved_at: datetime | None = None
  ```
- [ ] ORM `MemoryProposalRow`: add
  ```python
  pr_url: Mapped[str | None] = mapped_column(String(500))
  resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
  ```
- [ ] Migration `migrations/versions/a6b2memory02_memory_apply_fields.py`, `down_revision="a6b1memory01"` (confirm with `uv run alembic heads`):
  ```python
  def upgrade() -> None:
      op.add_column("memory_proposals", sa.Column("pr_url", sa.String(length=500), nullable=True))
      op.add_column("memory_proposals", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
  def downgrade() -> None:
      op.drop_column("memory_proposals", "resolved_at")
      op.drop_column("memory_proposals", "pr_url")
  ```
- [ ] Run `uv run pytest tests/unit/test_migrations.py` → parity green.
- [ ] Commit: `feat: MemoryProposal apply fields (pr_url, resolved_at) + migration`.

**Wave 1 gate:** `uv run ruff check src tests && uv run pytest -q` green.

---

## Wave 2

### Task 3 (Lane S): `MemoryApplier` + auto-apply in capture_memory

**Files:** create `src/interactors/memory_apply.py`; modify `src/interactors/temporal/activities.py`, `src/interactors/temporal/workflows.py`; tests `tests/unit/test_memory_applier.py`, `tests/workflow/test_capture_memory.py`, `tests/workflow/test_run_workflow.py`.

- [ ] Test (applier local): `MemoryApplier(FakeGit(), FakeGitForge(), profile="local").apply(proposal, repo_ref="/r", base="main")` returns a proposal with `status==APPLIED`, `resolved_at` set, `pr_url is None`; `git.merged_into_base` recorded.
- [ ] Test (applier remote): `profile="remote"` returns `status==APPLIED`, `pr_url == forge PR url`; `git.merged_into_base` empty.
- [ ] Implement `src/interactors/memory_apply.py`:
  ```python
  from domain.models import MemoryProposal, MemoryProposalStatus, utc_now

  class MemoryApplier:
      def __init__(self, git, forge, *, profile: str):
          self._git, self._forge, self._profile = git, forge, profile

      def apply(self, proposal: MemoryProposal, *, repo_ref: str, base: str) -> MemoryProposal:
          if self._profile == "remote":
              token = self._forge.installation_token()
              pr_url = self._forge.open_pull_request(
                  head=proposal.branch, base=base,
                  title=f"memory update for run {proposal.run_id}",
                  body="Automated project-memory update.")
              return proposal.model_copy(update={
                  "status": MemoryProposalStatus.APPLIED, "pr_url": pr_url,
                  "resolved_at": utc_now()})
          self._git.merge_into_base(repo_ref, branch=proposal.branch, base=base)
          return proposal.model_copy(update={
              "status": MemoryProposalStatus.APPLIED, "resolved_at": utc_now()})
  ```
  (Remote `installation_token()` call kept for parity with `open_pr`; forge impls that need auth use it.)
- [ ] Test (capture_memory auto): with `payload["autonomy"]=="full_auto"` and `FakeGit(memory_diff=...)`, after `capture_memory` the persisted proposal has `status=="applied"`; with `"gated_all"` it stays `"proposed"`.
- [ ] capture_memory: accept `payload["autonomy"]` and `payload["repo_ref"]`; after persisting the proposal, if `autonomy == "full_auto"`: build `MemoryApplier(self._git, self._forge, profile=payload["profile"])`, call `.apply(proposal, repo_ref=payload["repo_ref"], base=payload["base"])`, persist the returned proposal (update), emit a run_event; wrap in try/except (best-effort, never fail the run). Keep the existing proposed-path run_event for non-full_auto.
- [ ] workflows.py: add `"autonomy": inp["autonomy"], "repo_ref": inp["repo_ref"]` to the `capture_memory` activity payload.
- [ ] test_run_workflow.py: add `"repo_ref"` already present; add a `full_auto` assertion that the proposal is `applied` (extend the existing memory test or add one). Ensure `_input` carries `autonomy` (it does).
- [ ] Commit: `feat: MemoryApplier + auto-apply memory in full_auto`.

**Wave 2 gate:** suite green.

---

## Wave 3

### Task 4 (Lane API): apply/reject endpoints

**Files:** `src/interactors/api/routes/runs.py`, `src/interactors/api/deps.py`; test `tests/integration/test_run_memory_api.py`.

- [ ] deps: add a `memory_applier` dependency building `MemoryApplier` from settings:
  ```python
  def memory_applier(request: Request):
      s = request.app.state.settings
      from adapters.git.local_git import LocalGit
      from interactors.memory_apply import MemoryApplier
      from interactors.temporal.worker import _build_forge
      return MemoryApplier(LocalGit(), _build_forge(s.profile), profile=s.profile)
  ```
- [ ] Test (apply): seed run + project (local_path) + proposed proposal; `POST /runs/{id}/memory/apply` → 200, `data.status=="applied"`; second call → 409.
- [ ] Test (reject): `POST /runs/{id}/memory/reject` → 200, `data.status=="rejected"`, `resolved_at` set; 404 when no proposal.
- [ ] Endpoints in runs.py:
  ```python
  @router.post("/runs/{run_id}/memory/apply", status_code=202)
  def apply_run_memory(run_id: str, uow=Depends(get_uow),
                       applier=Depends(memory_applier), s=Depends(get_settings)) -> dict:
      with uow.transaction():
          run = uow.runs.get(run_id)
          page = uow.memory_proposals.list(filters={"run_id": run_id},
                                           order_by="-created_at", page_size=1)
          if not page.results:
              raise HTTPException(404, "no memory proposal")
          proposal = page.results[0]
          if proposal.status != MemoryProposalStatus.PROPOSED:
              raise HTTPException(409, f"proposal is {proposal.status}")
          project = uow.projects.get(proposal.project_id)
          repo_ref = project.local_path if s.profile == "local" else project.repo_url
          applied = applier.apply(proposal, repo_ref=repo_ref, base=s.github_base_branch)
          result = uow.memory_proposals.update(proposal.id, applied)
      return ok(result.model_dump(mode="json"))

  @router.post("/runs/{run_id}/memory/reject", status_code=202)
  def reject_run_memory(run_id: str, uow=Depends(get_uow)) -> dict:
      with uow.transaction():
          uow.runs.get(run_id)
          page = uow.memory_proposals.list(filters={"run_id": run_id},
                                           order_by="-created_at", page_size=1)
          if not page.results:
              raise HTTPException(404, "no memory proposal")
          proposal = page.results[0]
          if proposal.status != MemoryProposalStatus.PROPOSED:
              raise HTTPException(409, f"proposal is {proposal.status}")
          rejected = proposal.model_copy(update={
              "status": MemoryProposalStatus.REJECTED, "resolved_at": utc_now()})
          result = uow.memory_proposals.update(proposal.id, rejected)
      return ok(result.model_dump(mode="json"))
  ```
  Wrap `applier.apply` so `GitError`/`ForgeError` → `HTTPException(409, str(e))`. Import `MemoryProposalStatus`, `utc_now`, `memory_applier`.
- [ ] Commit: `feat: apply/reject memory proposal endpoints`.

### Task 5 (Lane UI): MemoryProposalCard

**Files:** create `ui/src/lib/api/memory.ts`, `ui/src/features/runs/useMemoryProposal.ts`, `ui/src/features/runs/MemoryProposalCard.tsx`, `ui/src/features/runs/MemoryProposalCard.test.tsx`; modify `ui/src/features/runs/RunSection.tsx`.

- [ ] api client `memory.ts`: `getRunMemory(runId)`, `applyRunMemory(runId)`, `rejectRunMemory(runId)` hitting `/runs/{id}/memory[/apply|/reject]`, unwrapping the envelope. Type `MemoryProposal { id, branch, diff, files, status, pr_url, resolved_at }`.
- [ ] hook `useMemoryProposal(runId)`: `useQuery` for the proposal + `useMutation` apply/reject invalidating the query.
- [ ] `MemoryProposalCard({ runId })`: if no proposal → render nothing. Show files + collapsible `<pre>` diff; `proposed` → Apply/Reject buttons; `applied`/`rejected` → badge; `pr_url` → link. Mirror `RunActions` styling.
- [ ] Render `<MemoryProposalCard runId={run.id} />` inside `RunSection` per run.
- [ ] Test (vitest + MSW): mock `GET /runs/r1/memory` returning a `proposed` proposal → card shows a file + Apply button; clicking Apply calls `POST .../apply` and the badge updates (or mutation fires). Mock null → renders nothing.
- [ ] Commit: `feat: memory proposal review card in run section`.

**Wave 3 gate:** `uv run ruff check src tests && uv run pytest -q` and `cd ui && node_modules/.bin/vitest run` green; `make coverage` ≥ 80%.

---

## Self-Review

**Spec coverage:** A→Task1; C→Task2; B→Task3; D→Task3; E→Task4; F→Task5. ✔
**Type consistency:** `merge_into_base(repo_ref, *, branch, base, token=None)->bool` identical across protocol/fake/local/applier/deps. `MemoryApplier.apply(proposal, *, repo_ref, base)->MemoryProposal` identical across unit test, capture_memory, endpoint. New fields `pr_url`/`resolved_at` consistent model↔row↔migration↔UI. ✔
**Placeholders:** none. UI test delegates MSW boilerplate to the existing `RunActions.test.tsx`/MSW setup pattern. ✔
