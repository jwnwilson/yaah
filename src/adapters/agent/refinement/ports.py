from typing import Protocol

from pydantic import BaseModel

from domain.models import ChatMessage, WorkItem
from domain.refinement import RefinementOutput


class RefinementContext(BaseModel):
    project_name: str
    history: list[ChatMessage] = []
    hierarchy: list[WorkItem] = []
    system_prompt: str = ""


class RefinementAgent(Protocol):
    def respond(self, ctx: RefinementContext) -> RefinementOutput: ...
