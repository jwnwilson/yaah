class FakeModelProvider:
    def agent_env(self) -> dict[str, str]:
        return {}

    def model_id(self) -> str:
        return "fake-model"
