"""Pure per-stage prompt + tool policy for the coding agent. No I/O."""

from domain.runs import RunStage

_EDIT_TOOLS = ["Read", "Edit", "Write", "Bash"]
_READ_TOOLS = ["Read", "Bash"]

_MEMORY_POINTER = (
    "Before you begin, read project memory if present: CLAUDE.md or AGENTS.md at the "
    "repo root, and any relevant files under docs/adr/. Honor the conventions, "
    "decisions, and gotchas recorded there.\n\n"
)


def memory_pointer(role, role_digest: str = "") -> str:
    """Prepended to an orchestrator agent's brief: revives the project-memory read pointer and
    (when role is known) injects the role digest + a self-authoring instruction."""
    base = (
        "Before you begin, read project memory if present: CLAUDE.md or AGENTS.md at the repo "
        "root, and relevant files under docs/adr/. Honor the conventions and gotchas there."
    )
    if role is None:
        return base + "\n\n"
    name = role.value if hasattr(role, "value") else str(role)
    digest = role_digest.strip() or "(none yet)"
    return (
        f"{base}\n\nYour accumulated {name} memory from past work:\n{digest}\n\n"
        f"If you learn something durable about working as {name}, append a concise note (one or "
        "two lines) to .orchestration/role-memory.md — only durable role-level knowledge, not "
        "task specifics.\n\n"
    )


def for_stage(stage: RunStage, task_title: str, acceptance_criteria: list[str],
              body: str = "") -> tuple[str, list[str]]:
    ac = "\n".join(f"- {c}" for c in acceptance_criteria)
    if stage == RunStage.PLAN:
        return (_MEMORY_POINTER +
                f"Read the ticket and write an implementation plan to plan.md.\n\n"
                f"Ticket: {task_title}\n{body}\n\nAcceptance criteria:\n{ac}",
                ["Read", "Write"])
    if stage == RunStage.IMPLEMENT:
        return (_MEMORY_POINTER +
                "Implement this ticket by editing the repository in the working directory.\n\n"
                f"Ticket: {task_title}\n{body}\n\nAcceptance criteria:\n{ac}",
                list(_EDIT_TOOLS))
    if stage == RunStage.VERIFY:
        return (
            "Verify the implementation satisfies the acceptance criteria. Run the tests/build. "
            f"Do NOT modify source files.\n\nAcceptance criteria:\n{ac}",
            list(_READ_TOOLS),
        )
    if stage == RunStage.LEARN:
        return (
            "Update project memory with durable learnings from this run. Edit CLAUDE.md "
            "or AGENTS.md at the repo root (keep each concise, ~120 lines max) and add or "
            "update entries under docs/adr/ for architectural decisions. Propose additions "
            "AND deletions: remove stale or wrong guidance, record new conventions and "
            "gotchas. Only durable, project-wide knowledge belongs here.\n\n"
            f"This run completed the ticket: {task_title}\n{body}\n\nAcceptance criteria:\n{ac}\n"
            "Record only durable, project-wide learnings — not this task's specifics.",
            ["Read", "Edit", "Write"],
        )
    # provision/pr are handled by dedicated activities, not the agent runtime
    return (f"{stage} stage for: {task_title}", ["Read"])


def max_turns(stage: RunStage) -> int:
    return {RunStage.IMPLEMENT: 40, RunStage.VERIFY: 20}.get(stage, 15)
