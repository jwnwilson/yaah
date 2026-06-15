from adapters.agent.model.anthropic import AnthropicProvider
from adapters.agent.model.fake import FakeModelProvider


def test_anthropic_env_and_model():
    p = AnthropicProvider(api_key="sk-test", model="claude-sonnet-4-6")
    assert p.agent_env()["ANTHROPIC_API_KEY"] == "sk-test"
    assert p.model_id() == "claude-sonnet-4-6"


def test_anthropic_passes_through_real_model_alias():
    p = AnthropicProvider(model="claude-sonnet-4-6")
    assert p.model_id("claude-opus-4-8") == "claude-opus-4-8"  # real id -> used as-is


def test_anthropic_falls_back_for_logical_alias():
    # A logical gateway alias (lead-model) is meaningless to `claude --model`; the default
    # team ships these, so direct-to-Anthropic must fall back to the configured model.
    p = AnthropicProvider(model="claude-sonnet-4-6")
    assert p.model_id("lead-model") == "claude-sonnet-4-6"


def test_litellm_resolves_alias_or_default():
    from adapters.agent.model.litellm import LiteLLMProvider
    p = LiteLLMProvider("http://litellm:4000", "sk", default_model="sonnet")
    assert p.model_id("engineer-model") == "engineer-model"  # gateway routes it
    assert p.model_id() == "sonnet"


def test_anthropic_env_empty_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert AnthropicProvider(api_key=None).agent_env() == {}


def test_fake_provider():
    f = FakeModelProvider()
    assert f.model_id() == "fake-model"
    assert f.agent_env() == {}


def test_litellm_provider_env_and_model():
    from adapters.agent.model.litellm import LiteLLMProvider
    p = LiteLLMProvider("http://litellm:4000", "sk-virt", default_model="sonnet")
    env = p.agent_env()
    assert env["ANTHROPIC_BASE_URL"] == "http://litellm:4000"
    assert env["ANTHROPIC_API_KEY"] == "sk-virt"
    assert p.model_id() == "sonnet"
