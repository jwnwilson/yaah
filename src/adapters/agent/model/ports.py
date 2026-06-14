from typing import Protocol


class ModelProvider(Protocol):
    """Supplies the agent subprocess's model connection (env) + model id.
    AnthropicProvider now; a LiteLLMProvider can drop in later (A5c)."""

    def agent_env(self) -> dict[str, str]: ...
    def model_id(self) -> str: ...
