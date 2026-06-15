from typing import Protocol

from domain.refinement import RefinementContext, RefinementOutput


class RefinementAgent(Protocol):
    def respond(self, ctx: RefinementContext) -> RefinementOutput: ...
