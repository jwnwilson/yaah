from domain.projects import WorkItemKind
from domain.refinement import (
    EpicSpecEdit,
    RefinementAction,
    RefinementContext,
    RefinementOutput,
    WorkItemProposal,
)

_APPROVALS = ("go", "yes", "start", "ship", "approve", "do it")


class FakeRefinementAgent:
    """Deterministic. An approval message ('go'/'yes'/…) commits. Otherwise, unscoped:
    drafts one epic; epic-scoped: drafts a child feature and proposes an epic spec edit."""

    def respond(self, ctx: RefinementContext) -> RefinementOutput:
        last = next((m.content for m in reversed(ctx.history) if m.role == "user"), "work")
        if last.strip().lower().startswith(_APPROVALS):
            return RefinementOutput(
                reply="Starting the committed work.",
                action=RefinementAction.COMMIT,
            )
        title = last.strip()[:60] or "work"
        if ctx.epic_id:
            return RefinementOutput(
                reply=f"Refined the epic and drafted a feature for: {title}",
                proposals=[
                    WorkItemProposal(
                        kind=WorkItemKind.FEATURE, parent_id=ctx.epic_id, title=title
                    )
                ],
                epic_update=EpicSpecEdit(
                    body=f"Spec: {title}", acceptance_criteria=[f"{title} works"]
                ),
            )
        return RefinementOutput(
            reply=f"Drafted an epic for: {title}",
            proposals=[WorkItemProposal(kind=WorkItemKind.EPIC, title=title)],
        )
