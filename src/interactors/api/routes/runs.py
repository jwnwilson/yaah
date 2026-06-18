from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from adapters.database.ports import UnitOfWork
from adapters.git.ports import ForgeError, GitError
from domain.agent.memory import MemoryProposalStatus
from domain.base import utc_now
from domain.errors import RecordNotFound
from domain.projects import WorkItemKind, WorkItemStatus
from domain.runs import RunStatus
from interactors.api.deps import get_uow, memory_applier, temporal_client
from interactors.api.deps import settings as get_settings
from interactors.api.envelope import ok
from interactors.cli.memory_apply import MemoryApplier
from interactors.scheduling import build_run_and_input
from interactors.temporal.client import TemporalRunClient

router = APIRouter(tags=["runs"])


@router.post("/work-items/{task_id}/runs", status_code=201)
def start_run(
    task_id: str,
    uow: UnitOfWork = Depends(get_uow),
    temporal: TemporalRunClient = Depends(temporal_client),
    settings=Depends(get_settings),
) -> dict:
    with uow.transaction():
        task = uow.work_items.get(task_id)
        if task.kind != WorkItemKind.TASK:
            raise HTTPException(status_code=404, detail="task not found")
        if task.status != WorkItemStatus.READY:
            raise HTTPException(status_code=409, detail=f"task is {task.status}, must be ready")
        project = uow.projects.get(task.project_id)
        if not project.team_id:
            raise HTTPException(status_code=409, detail="project has no team assigned")
        run, run_input = build_run_and_input(uow, settings, task, project)
    temporal.start_run_workflow(run_input, "OrchestratorWorkflow")  # after commit
    return ok(run.model_dump(mode="json"))


@router.get("/work-items/{task_id}/runs")
def list_runs(task_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        uow.work_items.get(task_id)
        page = uow.runs.list(filters={"task_id": task_id}, order_by="-created_at")
    return ok(
        [r.model_dump(mode="json") for r in page.results],
        meta={"total": page.total, "page_size": page.page_size, "page_number": page.page_number},
    )


@router.get("/runs")
def list_all_runs(uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        page = uow.runs.list(order_by="-created_at", page_size=100)
        titles: dict[str, str | None] = {}
        for tid in {r.task_id for r in page.results}:
            try:
                titles[tid] = uow.work_items.get(tid).title
            except RecordNotFound:
                titles[tid] = None
    return ok(
        [{**r.model_dump(mode="json"), "task_title": titles.get(r.task_id)}
         for r in page.results],
        meta={"total": page.total, "page_size": page.page_size,
              "page_number": page.page_number},
    )


@router.get("/runs/{run_id}")
def get_run(run_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        run = uow.runs.get(run_id)
    return ok(run.model_dump(mode="json"))


@router.get("/runs/{run_id}/events")
def list_run_events(run_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        uow.runs.get(run_id)  # 404 if unknown / cross-tenant
        page = uow.run_events.list(filters={"run_id": run_id}, order_by="created_at", page_size=200)
    return ok(
        [e.model_dump(mode="json") for e in page.results],
        meta={"total": page.total, "page_size": page.page_size, "page_number": page.page_number},
    )


@router.get("/runs/{run_id}/audit")
def list_run_audit(run_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        uow.runs.get(run_id)  # 404 if unknown / cross-tenant
        page = uow.audit_events.list(
            filters={"run_id": run_id}, order_by="created_at", page_size=200
        )
    return ok(
        [e.model_dump(mode="json") for e in page.results],
        meta={"total": page.total, "page_size": page.page_size, "page_number": page.page_number},
    )


@router.get("/runs/{run_id}/memory")
def get_run_memory(run_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        uow.runs.get(run_id)  # 404 if unknown / cross-tenant
        page = uow.memory_proposals.list(
            filters={"run_id": run_id}, order_by="-created_at", page_size=1)
    data = page.results[0].model_dump(mode="json") if page.results else None
    return ok(data)


def _proposed_or_error(uow: UnitOfWork, run_id: str):
    uow.runs.get(run_id)  # 404 if unknown / cross-tenant
    page = uow.memory_proposals.list(
        filters={"run_id": run_id}, order_by="-created_at", page_size=1)
    if not page.results:
        raise HTTPException(status_code=404, detail="no memory proposal")
    proposal = page.results[0]
    if proposal.status != MemoryProposalStatus.PROPOSED:
        raise HTTPException(status_code=409, detail=f"proposal is {proposal.status}")
    return proposal


@router.post("/runs/{run_id}/memory/apply", status_code=202)
def apply_run_memory(
    run_id: str,
    uow: UnitOfWork = Depends(get_uow),
    applier: MemoryApplier = Depends(memory_applier),
    settings=Depends(get_settings),
) -> dict:
    with uow.transaction():
        proposal = _proposed_or_error(uow, run_id)
        project = uow.projects.get(proposal.project_id)
        repo_ref = project.local_path if settings.profile == "local" else project.repo_url
        try:
            applied = applier.apply(proposal, repo_ref=repo_ref,
                                    base=settings.github_base_branch)
        except (GitError, ForgeError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        result = uow.memory_proposals.update(proposal.id, applied)
    return ok(result.model_dump(mode="json"))


@router.post("/runs/{run_id}/memory/reject", status_code=202)
def reject_run_memory(run_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        proposal = _proposed_or_error(uow, run_id)
        rejected = proposal.model_copy(update={
            "status": MemoryProposalStatus.REJECTED, "resolved_at": utc_now()})
        result = uow.memory_proposals.update(proposal.id, rejected)
    return ok(result.model_dump(mode="json"))


def _signal(
    run_id: str,
    name: str,
    *,
    require_gate: bool,
    uow: UnitOfWork,
    temporal: TemporalRunClient,
) -> dict:
    with uow.transaction():
        run = uow.runs.get(run_id)
        if require_gate and run.status != RunStatus.AWAITING_APPROVAL:
            raise HTTPException(
                status_code=409, detail=f"run is {run.status}, not awaiting approval"
            )
        terminal = (RunStatus.DONE, RunStatus.FAILED, RunStatus.CANCELLED)
        if not require_gate and run.status in terminal:
            raise HTTPException(status_code=409, detail=f"run is terminal ({run.status})")
    temporal.signal(run_id, name)
    return run.model_dump(mode="json")


@router.post("/runs/{run_id}/approve", status_code=202)
def approve_run(
    run_id: str,
    uow: UnitOfWork = Depends(get_uow),
    temporal: TemporalRunClient = Depends(temporal_client),
) -> dict:
    return ok(_signal(run_id, "approve", require_gate=True, uow=uow, temporal=temporal))


@router.post("/runs/{run_id}/reject", status_code=202)
def reject_run(
    run_id: str,
    uow: UnitOfWork = Depends(get_uow),
    temporal: TemporalRunClient = Depends(temporal_client),
) -> dict:
    return ok(_signal(run_id, "reject", require_gate=True, uow=uow, temporal=temporal))


@router.post("/runs/{run_id}/cancel", status_code=202)
def cancel_run(
    run_id: str,
    uow: UnitOfWork = Depends(get_uow),
    temporal: TemporalRunClient = Depends(temporal_client),
) -> dict:
    return ok(_signal(run_id, "cancel", require_gate=False, uow=uow, temporal=temporal))


class UpdateRun(BaseModel):
    stage: str | None = None
    branch: str | None = None
    pr_url: str | None = None


@router.patch("/runs/{run_id}")
def patch_run(run_id: str, body: UpdateRun, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        run = uow.runs.get(run_id)
        result = uow.runs.update(run_id, run.model_copy(update=body.model_dump(exclude_none=True)))
    return ok(result.model_dump(mode="json"))
