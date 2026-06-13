import os


class AnthropicProvider:
    """Default ModelProvider: the agent talks directly to Anthropic."""

    def __init__(self, api_key: str | None = None, model: str = "claude-sonnet-4-6"):
        self._api_key = api_key
        self._model = model

    def agent_env(self) -> dict[str, str]:
        key = self._api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        return {"ANTHROPIC_API_KEY": key} if key else {}

    def model_id(self) -> str:
        return self._model
