"""Pure refinement policy: proposal shapes, validation, system prompt. No I/O."""

from typing import Callable

from pydantic import BaseModel

from domain.models import ChatMessage, WorkItem, WorkItemKind


class WorkItemProposal(BaseModel):
    kind: WorkItemKind
    parent_id: str | None = None
    title: str
    body: str = ""
    acceptance_criteria: list[str] = []


class EpicSpecEdit(BaseModel):
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
            "propose is created as a Draft for human review — never mark anything ready.")


def epic_focus_prompt(epic: WorkItem) -> str:
    return (
        f"You are now refining the epic '{epic.title}' (id {epic.id}). Propose features "
        f"under this epic (parent_id={epic.id}) and tasks under those features. You may also "
        "return an epic_update to refine THIS epic's body and acceptance criteria. Everything "
        "is created as a Draft for human review — never mark anything ready."
    )
