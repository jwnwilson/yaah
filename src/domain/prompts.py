"""Pure per-stage prompt + tool policy for the coding agent. No I/O."""

from domain.models import RunStage

_EDIT_TOOLS = ["Read", "Edit", "Write", "Bash"]
_READ_TOOLS = ["Read", "Bash"]


def for_stage(stage: RunStage, task_title: str, acceptance_criteria: list[str],
              body: str = "") -> tuple[str, list[str]]:
    ac = "\n".join(f"- {c}" for c in acceptance_criteria)
    if stage == RunStage.PLAN:
        return (f"Read the ticket and write an implementation plan to plan.md.\n\n"
                f"Ticket: {task_title}\n{body}\n\nAcceptance criteria:\n{ac}",
                ["Read", "Write"])
    if stage == RunStage.IMPLEMENT:
        return (f"Implement this ticket by editing the repository in the working directory.\n\n"
                f"Ticket: {task_title}\n{body}\n\nAcceptance criteria:\n{ac}",
                list(_EDIT_TOOLS))
    if stage == RunStage.VERIFY:
        return (
            "Verify the implementation satisfies the acceptance criteria. Run the tests/build. "
            f"Do NOT modify source files.\n\nAcceptance criteria:\n{ac}",
            list(_READ_TOOLS),
        )
    if stage == RunStage.LEARN:
        return ("Summarise what changed in this run for project memory.", ["Read", "Write"])
    # provision/pr are handled by dedicated activities, not the agent runtime
    return (f"{stage} stage for: {task_title}", ["Read"])


def max_turns(stage: RunStage) -> int:
    return {RunStage.IMPLEMENT: 40, RunStage.VERIFY: 20}.get(stage, 15)
