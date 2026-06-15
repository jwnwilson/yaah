class LiteLLMProvider:
    """ModelProvider that points the agent at a LiteLLM gateway (Anthropic-compatible
    endpoint). model_id() is the default alias; per-agent routing overrides it via the
    manifest's model_alias."""

    def __init__(self, base_url: str, api_key: str, default_model: str = "sonnet"):
        self._base_url = base_url
        self._api_key = api_key
        self._default_model = default_model

    def agent_env(self) -> dict[str, str]:
        return {"ANTHROPIC_BASE_URL": self._base_url, "ANTHROPIC_API_KEY": self._api_key}

    def model_id(self, alias: str | None = None) -> str:
        # The gateway resolves logical aliases (lead-model, engineer-model, …) to real
        # models via its config; pass the per-agent alias through, default when unset.
        return alias or self._default_model
