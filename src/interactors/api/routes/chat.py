"""Synchronous refinement chat API routes."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from adapters.agent.refinement.ports import RefinementAgent
from adapters.database.ports import UnitOfWork
from domain.refinement import (
    ChatMessage,
    ChatRole,
    ChatSession,
    RefinementContext,
    epic_focus_prompt,
    system_prompt,
    validate_proposal,
)
from domain.work_items import WorkItem, WorkItemKind, WorkItemStatus
from interactors.api.deps import get_uow, refinement_agent
from interactors.api.envelope import ok

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
                )
            )
            created.append(item)

        proposed_epic_update = (
            out.epic_update.model_dump(mode="json")
            if epic_scope and out.epic_update
            else None
        )

        reply = out.reply + (("\n\nSkipped: " + "; ".join(notes)) if notes else "")

    return ok(
        {
            "session_id": session.id,
            "reply": reply,
            "created_items": [c.model_dump(mode="json") for c in created],
            "proposed_epic_update": proposed_epic_update,
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
