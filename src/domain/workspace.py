from typing import Protocol

from pydantic import BaseModel


class Workspace(BaseModel):
    run_id: str
    path: str


class WorkspaceProvider(Protocol):
    def provision(self, run_id: str) -> Workspace: ...
    def destroy(self, workspace: Workspace) -> None: ...
