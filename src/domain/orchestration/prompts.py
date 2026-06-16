"""The lead-decision contract: orchestrator prompt + parsing of the lead's structured
output into typed decisions/verdicts. Pure (no runtime/transport concerns). No I/O."""

from pydantic import ValidationError

from domain.models import AgentRole
from domain.orchestration.core import MonitorVerdict, OrchestrationDecision, OrchestrationState


class OrchestrationContractError(ValueError):
    """The lead's output did not satisfy the decision/verdict schema."""


# Keep in sync with OrchestrationIntent.
_INTENTS = (
    "continue (dispatch agents and keep going), "
    "verify (trigger the completion monitor), "
    "complete (only after a monitor pass), "
    "block (give up — requires a rationale), "
    "needs_human (open a human approval gate)"
)


# Pure "when to dispatch" hints, rendered next to the available roles so the lead
# knows what each role is for. Roles absent here fall back to their bare name.
_ROLE_GUIDE: dict[AgentRole, str] = {
    AgentRole.LEAD: "you — orchestrate; do not dispatch yourself",
    AgentRole.ARCHITECT: "review the plan/design and record decisions (no code)",
    AgentRole.BACKEND: "implement server/domain code",
    AgentRole.FRONTEND: "implement the ui/ frontend",
    AgentRole.QA: "verify the work against acceptance criteria (read-only)",
    AgentRole.DEVOPS: "CI/Docker/deploy config and CI-failure triage",
}


# Security: task_title/body are user-controlled and interpolated into the lead prompt;
# callers must trust-scope or sanitise input (hardening tracked for the runtime layer).
def build_orchestrator_prompt(
    *,
    task_title: str,
    acceptance_criteria: list[str],
    body: str,
    state: OrchestrationState,
    available_roles: list[AgentRole],
) -> str:
    ac = "\n".join(f"- {c}" for c in acceptance_criteria) or "- (none given)"
    roles = "\n".join(
        f"- {r.value}: {_ROLE_GUIDE.get(r, r.value)}" for r in available_roles
    ) or "- (none)"
    reports = "\n".join(
        f"- {r.role.value}: {r.outcome.value} — {r.summary}" for r in state.reports
    ) or "- (no reports yet)"
    last = state.verdicts[-1] if state.verdicts else None
    feedback = ""
    if last is not None and not last.complete:
        items = "\n".join(f"- {u}" for u in last.unmet) or f"- {last.notes}"
        feedback = (
            "\n\nVerification feedback — these acceptance criteria are NOT yet met; "
            f"dispatch work to fix them, then verify again:\n{items}"
        )
    integration = ""
    if state.last_integration:
        files = ", ".join(state.last_integration.get("files", [])) or "(unknown files)"
        integration = (
            "\n\nIntegration conflict — the branch "
            f"{state.last_integration.get('branch', '?')} could not be merged (conflicting "
            f"files: {files}). Re-dispatch one engineer to resolve it against the integrated "
            "base, then verify."
        )
    return (
        "You are the team lead orchestrating a software task. Decide the next step; you do "
        "NOT do the work yourself. Respond ONLY with a JSON object matching the decision "
        "schema.\n\n"
        f"Ticket: {task_title}\n{body}\n\nAcceptance criteria:\n{ac}\n\n"
        f"Available agent roles you may dispatch:\n{roles}\n\n"
        f"Progress so far — wave {state.waves}, dispatches {state.total_dispatches}, "
        f"cost ${state.total_cost_usd:.2f}.\nReports:\n{reports}{feedback}{integration}\n\n"
        f"Choose one intent: {_INTENTS}.\n"
        "Decision JSON fields: intent (required); dispatches (list of "
        "{target_role, instructions, acceptance[]}); "
        "dispatches may set memory_scope ('project' default, or 'all' to draw on that role's "
        "memory from every project for a large or cross-cutting task). "
        "messages (list of "
        "{recipient_kind: agent|user, recipient_role?, kind?, subject?, body}); "
        "assignee_role (the role primarily responsible); rationale (required for block). "
        "When all work appears done, use intent=verify to have the monitor confirm before "
        "you complete."
    )


def parse_decision(raw: dict) -> OrchestrationDecision:
    """Validate the lead's raw output into a typed decision, or raise a contract error."""
    try:
        return OrchestrationDecision.model_validate(raw)
    except ValidationError as exc:
        raise OrchestrationContractError(str(exc)) from exc


def parse_verdict(raw: dict) -> MonitorVerdict:
    """Validate the monitor's raw output into a typed verdict, or raise a contract error."""
    try:
        return MonitorVerdict.model_validate(raw)
    except ValidationError as exc:
        raise OrchestrationContractError(str(exc)) from exc
