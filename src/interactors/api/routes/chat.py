"""Synchronous refinement chat API routes."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from adapters.agent.refinement.ports import RefinementAgent
from adapters.database.ports import UnitOfWork
from domain.base import utc_now
from domain.projects import WorkItem, WorkItemKind, WorkItemStatus
from domain.refinement import (
    ChatMessage,
    ChatRole,
    ChatSession,
    RefinementAction,
    RefinementContext,
    epic_focus_prompt,
    select_committable,
    system_prompt,
    validate_proposal,
)
from domain.transitions import InvalidTransition, validate_transition
from interactors.api.deps import get_uow, refinement_agent, temporal_client
from interactors.api.deps import settings as get_settings
from interactors.api.envelope import ok
from interactors.scheduling import reconcile_project
from interactors.temporal.client import TemporalRunClient

router = APIRouter(tags=["chat"])


class PostMessage(BaseModel):
    message: str
    session_id: str | None = None
    epic_id: str | None = None


@router.post("/projects/{project_id}/chat")
def post_message(
    project_id: str,
    body: PostMessage,
    uow: UnitOfWork = Depends(get_uow),
    agent: RefinementAgent = Depends(refinement_agent),
    temporal: TemporalRunClient = Depends(temporal_client),
    settings=Depends(get_settings),
) -> dict:
    with uow.transaction():
        project = uow.projects.get(project_id)  # RecordNotFound -> 404

        if body.session_id:
            session = uow.chat_sessions.get(body.session_id)
        else:
            session = uow.chat_sessions.create(
                ChatSession(
                    owner_id=project.owner_id,
                    project_id=project_id,
                    epic_id=body.epic_id,
                )
            )

        uow.chat_messages.create(
            ChatMessage(
                owner_id=project.owner_id,
                session_id=session.id,
                role=ChatRole.USER,
                content=body.message,
            )
        )

        history = uow.chat_messages.list(
            filters={"session_id": session.id},
            order_by="created_at",
            page_size=100,
        ).results

        epic_scope = session.epic_id
        if epic_scope:
            epic = uow.work_items.get(epic_scope)
            features = uow.work_items.list(
                filters={
                    "project_id": project_id,
                    "parent_id": epic.id,
                    "kind": WorkItemKind.FEATURE,
                },
                page_size=200,
            ).results
            parent_ids = [epic.id, *(f.id for f in features)]
            tasks = [
                t
                for parent_id in parent_ids
                for t in uow.work_items.list(
                    filters={
                        "project_id": project_id,
                        "parent_id": parent_id,
                        "kind": WorkItemKind.TASK,
                    },
                    page_size=200,
                ).results
            ]
            hierarchy = [epic, *features, *tasks]
            prompt = system_prompt(project.name) + "\n\n" + epic_focus_prompt(epic)
        else:
            hierarchy = uow.work_items.list(
                filters={"project_id": project_id}, page_size=200
            ).results
            prompt = system_prompt(project.name)

        ctx = RefinementContext(
            project_name=project.name,
            history=history,
            hierarchy=hierarchy,
            system_prompt=prompt,
            epic_id=epic_scope,
        )
        out = agent.respond(ctx)

        uow.chat_messages.create(
            ChatMessage(
                owner_id=project.owner_id,
                session_id=session.id,
                role=ChatRole.ASSISTANT,
                content=out.reply,
            )
        )

        existing_ids = {w.id for w in hierarchy}
        created: list[WorkItem] = []
        notes: list[str] = []

        for proposal in out.proposals:
            try:
                validate_proposal(
                    proposal,
                    parent_exists=lambda pid: pid in existing_ids
                    or any(c.id == pid for c in created),
                )
            except ValueError as exc:
                notes.append(str(exc))
                continue

            item = uow.work_items.create(
                WorkItem(
                    project_id=project_id,
                    owner_id=project.owner_id,
                    kind=proposal.kind,
                    parent_id=proposal.parent_id,
                    title=proposal.title,
                    body=proposal.body,
                    acceptance_criteria=proposal.acceptance_criteria,
                    status=WorkItemStatus.DRAFT,  # NEVER ready
                    chat_session_id=session.id,
                )
            )
            created.append(item)

        proposed_epic_update = (
            out.epic_update.model_dump(mode="json")
            if epic_scope and out.epic_update
            else None
        )

        # Edits to existing items are proposed, never applied here. Validate each id is a
        # known item in the loaded hierarchy; attach its current kind/title for display.
        by_id = {w.id: w for w in hierarchy}
        proposed_updates: list[dict] = []
        for upd in out.updates:
            item = by_id.get(upd.id)
            if item is None:
                notes.append(f"unknown item {upd.id}")
                continue
            proposed_updates.append({
                "id": item.id,
                "kind": item.kind.value,
                "current_title": item.title,
                "title": upd.title,
                "body": upd.body,
                "acceptance_criteria": upd.acceptance_criteria,
            })

        run_inputs: list[dict] = []
        if out.action == RefinementAction.COMMIT:
            session_items = uow.work_items.list(
                filters={"project_id": project_id, "chat_session_id": session.id},
                page_size=500,
            ).results
            plan = select_committable(session_items)
            by_session_id = {i.id: i for i in session_items}
            for tid in plan.task_ids:
                task = by_session_id[tid]
                try:
                    validate_transition(task.status, WorkItemStatus.READY)
                except InvalidTransition as exc:
                    notes.append(str(exc))
                    continue
                uow.work_items.update(
                    tid,
                    task.model_copy(
                        update={"status": WorkItemStatus.READY, "updated_at": utc_now()}
                    ),
                )
            for pid in plan.parent_ids:
                parent = uow.work_items.get(pid)
                if parent.kind in (WorkItemKind.EPIC, WorkItemKind.FEATURE) and not parent.active:
                    uow.work_items.update(
                        pid,
                        parent.model_copy(update={"active": True, "updated_at": utc_now()}),
                    )
            run_inputs = reconcile_project(uow, settings, project_id)

        reply = out.reply + (("\n\nSkipped: " + "; ".join(notes)) if notes else "")

    for ri in run_inputs:
        temporal.start_run_workflow(ri, "OrchestratorWorkflow")

    return ok(
        {
            "session_id": session.id,
            "reply": reply,
            "created_items": [c.model_dump(mode="json") for c in created],
            "proposed_epic_update": proposed_epic_update,
            "proposed_updates": proposed_updates,
            "started_runs": [ri["run_id"] for ri in run_inputs],
        }
    )


@router.get("/projects/{project_id}/chat")
def list_sessions(
    project_id: str,
    uow: UnitOfWork = Depends(get_uow),
) -> dict:
    with uow.transaction():
        uow.projects.get(project_id)  # RecordNotFound -> 404
        page = uow.chat_sessions.list(
            filters={"project_id": project_id},
            order_by="-created_at",
        )
    return ok(
        [s.model_dump(mode="json") for s in page.results],
        meta={
            "total": page.total,
            "page_size": page.page_size,
            "page_number": page.page_number,
        },
    )


@router.get("/chat/{session_id}/messages")
def list_messages(
    session_id: str,
    page_size: int = Query(200, ge=1, le=500),
    uow: UnitOfWork = Depends(get_uow),
) -> dict:
    with uow.transaction():
        uow.chat_sessions.get(session_id)  # RecordNotFound -> 404 (also owner-scoped)
        page = uow.chat_messages.list(
            filters={"session_id": session_id},
            order_by="created_at",
            page_size=page_size,
        )
    return ok(
        [m.model_dump(mode="json") for m in page.results],
        meta={
            "total": page.total,
            "page_size": page.page_size,
            "page_number": page.page_number,
        },
    )
