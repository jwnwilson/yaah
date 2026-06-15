import os


class AnthropicProvider:
    """Default ModelProvider: the agent talks directly to Anthropic."""

    def __init__(self, api_key: str | None = None, model: str = "claude-sonnet-4-6"):
        self._api_key = api_key
        self._model = model

    def agent_env(self) -> dict[str, str]:
        key = self._api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        return {"ANTHROPIC_API_KEY": key} if key else {}

    def model_id(self, alias: str | None = None) -> str:
        # A real Anthropic model id (e.g. "claude-sonnet-4-6") is usable directly as
        # `claude --model`. A logical gateway alias (e.g. "lead-model") is meaningless to
        # the Claude CLI, so fall back to the configured model. Per-role logical aliases
        # require the LiteLLM gateway.
        if alias and alias.startswith("claude-"):
            return alias
        return self._model
