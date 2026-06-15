import httpx

from adapters.agent.model.ports import ModelProvider
from domain.refinement import RefinementContext, RefinementOutput

# The tool's input_schema is derived from the domain model so the proposal shape has a
# single source of truth (domain.refinement) and never drifts from it. The name/description
# are the Anthropic tool-use wrapper — the one genuinely adapter-specific part.
_TOOL = {
    "name": "propose",
    "description": "Reply to the user and propose work items to draft.",
    "input_schema": RefinementOutput.model_json_schema(),
}


class AnthropicRefinementAgent:
    def __init__(self, model: ModelProvider) -> None:
        self._model = model

    def _client_factory(self) -> httpx.Client:  # overridden in tests
        return httpx.Client(timeout=60)

    def _base_url(self) -> str:
        return self._model.agent_env().get(
            "ANTHROPIC_BASE_URL", "https://api.anthropic.com"
        )

    def respond(self, ctx: RefinementContext) -> RefinementOutput:
        env = self._model.agent_env()
        msgs = [{"role": m.role, "content": m.content} for m in ctx.history]
        body = {
            "model": self._model.model_id(),
            "max_tokens": 2000,
            "system": ctx.system_prompt,
            "messages": msgs,
            "tools": [_TOOL],
            "tool_choice": {"type": "tool", "name": "propose"},
        }
        with self._client_factory() as c:
            r = c.post(
                f"{self._base_url()}/v1/messages",
                json=body,
                headers={
                    "x-api-key": env.get("ANTHROPIC_API_KEY", ""),
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
            )
        if r.status_code >= 300:
            return RefinementOutput(reply="(refinement unavailable)", proposals=[])
        for block in r.json().get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == "propose":
                return RefinementOutput(**block["input"])
        return RefinementOutput(reply="(no proposal)", proposals=[])
