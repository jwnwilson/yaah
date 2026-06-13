from adapters.refinement.ports import RefinementContext
from domain.models import WorkItemKind
from domain.refinement import RefinementOutput, WorkItemProposal


class FakeRefinementAgent:
    """Deterministic: echoes the last user message as one drafted epic."""

    def respond(self, ctx: RefinementContext) -> RefinementOutput:
        last = next(
            (m.content for m in reversed(ctx.history) if m.role == "user"), "work"
        )
        title = last.strip()[:60] or "work"
        return RefinementOutput(
            reply=f"Drafted an epic for: {title}",
            proposals=[WorkItemProposal(kind=WorkItemKind.EPIC, title=title)],
        )
