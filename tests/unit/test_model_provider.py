from adapters.model.anthropic import AnthropicProvider
from adapters.model.fake import FakeModelProvider


def test_anthropic_env_and_model():
    p = AnthropicProvider(api_key="sk-test", model="claude-sonnet-4-6")
    assert p.agent_env()["ANTHROPIC_API_KEY"] == "sk-test"
    assert p.model_id() == "claude-sonnet-4-6"


def test_anthropic_env_empty_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert AnthropicProvider(api_key=None).agent_env() == {}


def test_fake_provider():
    f = FakeModelProvider()
    assert f.model_id() == "fake-model"
    assert f.agent_env() == {}


def test_litellm_provider_env_and_model():
    from adapters.model.litellm import LiteLLMProvider
    p = LiteLLMProvider("http://litellm:4000", "sk-virt", default_model="sonnet")
    env = p.agent_env()
    assert env["ANTHROPIC_BASE_URL"] == "http://litellm:4000"
    assert env["ANTHROPIC_API_KEY"] == "sk-virt"
    assert p.model_id() == "sonnet"
