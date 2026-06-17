"""Role-memory + memory-proposal entities, project-memory paths, and diff helpers.
Pure; no I/O."""
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from domain.agent.models import AgentRole
from domain.base import new_id, utc_now


class RoleMemoryEntry(BaseModel):
    """One durable, append-only role-level learning. Owner-scoped; cross-project (project_id
    records origin but reads can span projects)."""

    id: str = Field(default_factory=new_id)
    owner_id: str
    role: AgentRole
    content: str
    run_id: str | None = None
    project_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class MemoryProposalStatus(StrEnum):
    PROPOSED = "proposed"
    APPLIED = "applied"
    REJECTED = "rejected"


class MemoryProposal(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    run_id: str
    project_id: str
    branch: str
    diff: str = ""
    files: list[str] = Field(default_factory=list)
    status: MemoryProposalStatus = MemoryProposalStatus.PROPOSED
    pr_url: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)


# The bounded set the harness captures and commits. Curator edits outside these
# paths are ignored (structural blast-radius guard).
MEMORY_PATHS: list[str] = ["CLAUDE.md", "AGENTS.md", "docs/adr"]

_NEW_FILE_MARKER = "+++ b/"


def changed_files(diff: str) -> list[str]:
    """Paths from the '+++ b/<path>' lines of a unified diff, in order."""
    files: list[str] = []
    for line in diff.splitlines():
        if line.startswith(_NEW_FILE_MARKER):
            files.append(line[len(_NEW_FILE_MARKER):])
    return files


def role_memory_digest(entries, *, max_entries: int, max_chars: int) -> str:
    """Render up to `max_entries` role-memory entries (caller-ordered, newest first) into a
    bounded markdown list, stopping before exceeding `max_chars`. Pure."""
    lines: list[str] = []
    used = 0
    for entry in entries[:max_entries]:
        block = f"- {entry.content.strip()}"
        if lines and used + len(block) + 1 > max_chars:
            break
        if not lines and len(block) > max_chars:
            break
        used += len(block) + (1 if lines else 0)
        lines.append(block)
    return "\n".join(lines)
