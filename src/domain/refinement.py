"""Chat-session entities + pure refinement policy: proposal shapes, validation,
system prompt. No I/O."""

from datetime import datetime
from enum import StrEnum
from typing import Callable

from pydantic import BaseModel, Field

from domain.base import new_id, utc_now
from domain.projects import WorkItem, WorkItemKind, WorkItemStatus


class RefinementAction(StrEnum):
    DISCUSS = "discuss"
    COMMIT = "commit"


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatSession(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    project_id: str
    epic_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class ChatMessage(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    session_id: str
    role: ChatRole
    content: str
    created_at: datetime = Field(default_factory=utc_now)


class WorkItemProposal(BaseModel):
    kind: WorkItemKind
    parent_id: str | None = None
    title: str
    body: str = ""
    acceptance_criteria: list[str] = []


class EpicSpecEdit(BaseModel):
    body: str | None = None
    acceptance_criteria: list[str] | None = None


class WorkItemEdit(BaseModel):
    """A proposed content edit to an EXISTING work item (any kind), addressed by id.
    Content only — never status. Applied only after human approval."""

    id: str
    title: str | None = None
    body: str | None = None
    acceptance_criteria: list[str] | None = None


class RefinementContext(BaseModel):
    """Input contract for a refinement turn: the project, conversation so far, current
    board hierarchy, and the lead system prompt."""

    project_name: str
    history: list[ChatMessage] = []
    hierarchy: list[WorkItem] = []
    system_prompt: str = ""
    epic_id: str | None = None


class RefinementOutput(BaseModel):
    reply: str = ""
    proposals: list[WorkItemProposal] = []
    epic_update: EpicSpecEdit | None = None
    updates: list[WorkItemEdit] = []
    action: RefinementAction = RefinementAction.DISCUSS


def validate_proposal(p: WorkItemProposal, *, parent_exists: Callable[[str], bool]) -> None:
    if p.kind == WorkItemKind.EPIC:
        if p.parent_id:
            raise ValueError("epic cannot have a parent")
        return
    if not p.parent_id:
        raise ValueError(f"{p.kind} requires a parent_id")
    if not parent_exists(p.parent_id):
        raise ValueError(f"parent {p.parent_id} not found")


def system_prompt(project_name: str, lead_system_prompt: str = "") -> str:
    base = (lead_system_prompt + "\n\n") if lead_system_prompt else ""
    return (f"{base}You are the team lead refining work for project '{project_name}'. "
            "Converse with the user and propose epics, features, and tasks to draft onto the "
            "board. Features and tasks must reference an existing parent id. Everything you "
            "propose is created as a Draft for human review — never mark anything ready. "
            "You may also propose edits to EXISTING items (epics, features, or tasks) by "
            "returning `updates`, each with the item's id and any of title/body/"
            "acceptance_criteria — content only, never status. Proposed edits are shown to the "
            "human for approval before they apply.")


def epic_focus_prompt(epic: WorkItem) -> str:
    return (
        f"You are now refining the epic '{epic.title}' (id {epic.id}). Propose features "
        f"under this epic (parent_id={epic.id}) and tasks under those features. You may also "
        "return an epic_update to refine THIS epic's body and acceptance criteria. Everything "
        "is created as a Draft for human review — never mark anything ready."
    )


class CommitPlan(BaseModel):
    """What a `commit` turn should start: the DRAFT tasks to mark READY and the direct
    parent ids to activate so the scheduler can see them. Pure — no I/O."""

    task_ids: list[str] = []
    parent_ids: list[str] = []


def select_committable(items: list[WorkItem]) -> CommitPlan:
    """Given a chat session's work items, pick the DRAFT tasks to promote and the distinct
    direct-parent ids that must be activated. Non-DRAFT items are ignored (idempotent)."""
    drafts = [
        i for i in items
        if i.kind == WorkItemKind.TASK and i.status == WorkItemStatus.DRAFT
    ]
    parent_ids: list[str] = []
    for t in drafts:
        if t.parent_id and t.parent_id not in parent_ids:
            parent_ids.append(t.parent_id)
    return CommitPlan(task_ids=[t.id for t in drafts], parent_ids=parent_ids)
