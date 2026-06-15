class FakeModelProvider:
    def agent_env(self) -> dict[str, str]:
        return {}

    def model_id(self, alias: str | None = None) -> str:
        return alias or "fake-model"
