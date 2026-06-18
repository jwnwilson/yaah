import tempfile
from pathlib import Path

from adapters.agent.runtime.fake import FakeAgentRuntime
from adapters.storage.local import LocalStorageAdapter
from interactors.api.settings import Settings
from interactors.temporal.worker import _build_runtime, _build_storage, build_activities


def test_build_storage_uses_settings_storage_dir():
    # The worker must build storage from settings.storage_dir (the single source of truth
    # shared with the API), NOT a hardcoded cwd-relative path that nests in the repo.
    s = Settings(_env_file=None, storage_dir=tempfile.mkdtemp())
    storage = _build_storage(s)
    resolved = Path(storage.local_path("runs/r1"))
    assert resolved == Path(s.storage_dir).resolve() / "runs" / "r1"


def test_build_activities_returns_all_registered():
    acts = build_activities("sqlite:///:memory:", profile="local")
    # 8 run activities + curate_memory + 4 orchestration activities
    # (persist_messages, invoke_lead, agent_step, run_monitor) + 3 parallel-engineer
    # activities (provision_engineer_workspace, integrate_branches, commit_engineer_branch)
    # + reconcile_project_runs.
    assert len(acts) == 17
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
    from adapters.agent.model.litellm import LiteLLMProvider
    from interactors.temporal.worker import _build_model_provider
    s = Settings(_env_file=None, model_gateway="litellm",
                 litellm_base_url="http://litellm:4000", litellm_api_key="sk-x")
    assert isinstance(_build_model_provider(s), LiteLLMProvider)


def test_build_model_provider_auto_falls_back_to_anthropic():
    from adapters.agent.model.anthropic import AnthropicProvider
    from interactors.temporal.worker import _build_model_provider
    s = Settings(_env_file=None, model_gateway="auto", litellm_base_url=None)
    assert isinstance(_build_model_provider(s), AnthropicProvider)


def test_build_runtime_claude_code_when_selected(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _b: "/usr/bin/claude")
    s = Settings(_env_file=None, agent_runtime="claude_code", anthropic_api_key="sk-x")
    rt = _build_runtime(s, LocalStorageAdapter(base_dir=tempfile.mkdtemp()))
    from adapters.agent.runtime.claude_code import ClaudeCodeRuntime
    assert isinstance(rt, ClaudeCodeRuntime)


def test_build_forge_prefers_pat_when_token_set(monkeypatch):
    from adapters.git.github_token import GitHubTokenForge
    from interactors.temporal.worker import _build_forge
    monkeypatch.setenv("YAAH_GITHUB_TOKEN", "ghp_x")
    monkeypatch.setenv("YAAH_GITHUB_REPO", "o/r")
    assert isinstance(_build_forge("remote"), GitHubTokenForge)
