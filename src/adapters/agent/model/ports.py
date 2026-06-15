from typing import Protocol


class ModelProvider(Protocol):
    """Supplies the agent subprocess's model connection (env) + model id.
    AnthropicProvider now; a LiteLLMProvider can drop in later (A5c)."""

    def agent_env(self) -> dict[str, str]: ...

    def model_id(self, alias: str | None = None) -> str:
        """Resolve the model the agent runs as. `alias` is the per-agent `model_alias`
        (a logical name); each provider resolves it appropriately (LiteLLM routes it;
        Anthropic uses it only if it's a real model id)."""
        ...
