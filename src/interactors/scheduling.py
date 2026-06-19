"""Run-scheduling use-cases: build a run from a task and reconcile a project's active epics
against its concurrency cap. The DB is the source of truth; callers launch the returned
run-inputs after the transaction commits."""
from domain.base import utc_now
from domain.projects import WorkItemKind, WorkItemStatus
from domain.projects.scheduling import order_ready_tasks, plan_starts
from domain.runs import Run, RunStatus

_NON_TERMINAL = [
    RunStatus.PENDING, RunStatus.RUNNING, RunStatus.AWAITING_APPROVAL, RunStatus.BLOCKED,
]


def build_run_and_input(uow, settings, task, project) -> tuple[Run, dict]:
    """Create the Run row, move the task to IN_PROGRESS, and build the workflow input.
    Caller must hold an open transaction and have validated task/project."""
    team_agents = uow.agents.list(filters={"team_id": project.team_id}, page_size=100).results
    available_roles = sorted({a.role.value for a in team_agents})
    role_to_agent_id = {a.role.value: a.id for a in team_agents}
    run = uow.runs.create(Run(owner_id=project.owner_id, task_id=task.id, team_id=project.team_id))
    uow.work_items.update(
        task.id,
        task.model_copy(update={"status": WorkItemStatus.IN_PROGRESS, "updated_at": utc_now()}),
    )
    repo_ref = project.local_path if settings.profile == "local" else project.repo_url
    run_input = {
        "run_id": run.id,
        "owner_id": run.owner_id,
        "task_id": task.id,
        "project_id": project.id,
        "autonomy": project.autonomy,
        "task_title": task.title,
        "acceptance_criteria": task.acceptance_criteria,
        "body": task.body,
        "profile": settings.profile,
        "repo_ref": repo_ref,
        "base": settings.github_base_branch,
        "team_id": run.team_id,
        "available_roles": available_roles,
        "role_to_agent_id": role_to_agent_id,
    }
    return run, run_input


def _in_flight_count(uow, project_id: str) -> int:
    task_ids = [
        t.id for t in uow.work_items.list(
            filters={"project_id": project_id, "kind": WorkItemKind.TASK}, page_size=1000
        ).results
    ]
    if not task_ids:
        return 0
    return uow.runs.list(
        filters={"task_id__in": task_ids, "status__in": [s.value for s in _NON_TERMINAL]},
        page_size=1,
    ).total


def reconcile_project(uow, settings, project_id: str) -> list[dict]:
    """Within an open transaction: lock the project, find READY tasks under active epics, and
    start as many as free slots allow. Returns run-inputs for the caller to launch post-commit."""
    project = uow.projects.get(project_id, for_update=True)
    if not project.team_id:
        return []
    epics = uow.work_items.list(
        filters={"project_id": project_id, "kind": WorkItemKind.EPIC, "active": True},
        page_size=200,
    ).results
    active_features = uow.work_items.list(
        filters={"project_id": project_id, "kind": WorkItemKind.FEATURE, "active": True},
        page_size=500,
    ).results
    epic_ids = [e.id for e in epics]
    features_under_active_epics = (
        uow.work_items.list(
            filters={
                "project_id": project_id, "kind": WorkItemKind.FEATURE, "parent_id__in": epic_ids,
            },
            page_size=500,
        ).results
        if epic_ids
        else []
    )
    # A task is eligible when its epic is active, or its feature is active (union).
    features = list({f.id: f for f in (*features_under_active_epics, *active_features)}.values())
    parent_ids = epic_ids + [f.id for f in features]
    if not parent_ids:
        return []
    ready_tasks = uow.work_items.list(
        filters={
            "project_id": project_id, "kind": WorkItemKind.TASK,
            "status": WorkItemStatus.READY, "parent_id__in": parent_ids,
        },
        page_size=500,
    ).results
    if not ready_tasks:
        return []
    in_flight = _in_flight_count(uow, project_id)
    ordered_ids = order_ready_tasks(ready_tasks, epics, features)
    to_start = plan_starts(ordered_ids, in_flight, project.max_concurrent_runs)
    by_id = {t.id: t for t in ready_tasks}
    return [build_run_and_input(uow, settings, by_id[tid], project)[1] for tid in to_start]
