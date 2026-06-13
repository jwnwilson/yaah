import tempfile

from adapters.runtime.fake import FakeAgentRuntime
from adapters.storage.local import LocalStorageAdapter
from interactors.api.settings import Settings
from interactors.temporal.worker import _build_runtime, build_activities


def test_build_activities_returns_six():
    acts = build_activities("sqlite:///:memory:", profile="local")
    assert len(acts) == 6
    assert all(callable(a) for a in acts)


def test_build_runtime_fake_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    s = Settings(_env_file=None, agent_runtime="auto", anthropic_api_key=None)
    rt = _build_runtime(s, LocalStorageAdapter(base_dir=tempfile.mkdtemp()))
    assert isinstance(rt, FakeAgentRuntime)


def test_build_runtime_forced_fake(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    s = Settings(_env_file=None, agent_runtime="fake")
    rt = _build_runtime(s, LocalStorageAdapter(base_dir=tempfile.mkdtemp()))
    assert isinstance(rt, FakeAgentRuntime)


def test_build_model_provider_selects_litellm(monkeypatch):
    from adapters.model.litellm import LiteLLMProvider
    from interactors.temporal.worker import _build_model_provider
    s = Settings(_env_file=None, model_gateway="litellm",
                 litellm_base_url="http://litellm:4000", litellm_api_key="sk-x")
    assert isinstance(_build_model_provider(s), LiteLLMProvider)


def test_build_model_provider_auto_falls_back_to_anthropic():
    from adapters.model.anthropic import AnthropicProvider
    from interactors.temporal.worker import _build_model_provider
    s = Settings(_env_file=None, model_gateway="auto", litellm_base_url=None)
    assert isinstance(_build_model_provider(s), AnthropicProvider)


def test_build_runtime_claude_code_when_selected(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _b: "/usr/bin/claude")
    s = Settings(_env_file=None, agent_runtime="claude_code", anthropic_api_key="sk-x")
    rt = _build_runtime(s, LocalStorageAdapter(base_dir=tempfile.mkdtemp()))
    from adapters.runtime.claude_code import ClaudeCodeRuntime
    assert isinstance(rt, ClaudeCodeRuntime)
