from pathlib import Path

from interactors.api.settings import Settings


def test_settings_defaults_to_local_dev():
    s = Settings(_env_file=None)
    assert s.profile == "local"
    assert s.auth_mode == "dev"
    assert s.database_url.startswith("postgresql+psycopg://")


def test_storage_dir_defaults_outside_any_repo():
    # Agent workspaces must not nest inside a git repo: a capable agent can walk up the tree
    # and edit the enclosing repo. The default must be an absolute path under the user's home,
    # not a cwd-relative path that lands inside whatever repo the worker runs from.
    s = Settings(_env_file=None)
    storage = Path(s.storage_dir)
    assert storage.is_absolute()
    assert storage == Path.home() / ".yaah" / "workspaces"


def test_storage_dir_reads_env(monkeypatch):
    monkeypatch.setenv("YAAH_STORAGE_DIR", "/srv/yaah/ws")
    assert Settings(_env_file=None).storage_dir == "/srv/yaah/ws"


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("YAAH_PROFILE", "remote")
    monkeypatch.setenv("YAAH_AUTH_MODE", "auth0")
    s = Settings(_env_file=None)
    assert s.profile == "remote"
    assert s.auth_mode == "auth0"


def test_github_settings_default_none():
    from interactors.api.settings import Settings
    s = Settings(_env_file=None)
    assert s.github_app_id is None
    assert s.github_base_branch == "main"


def test_agent_runtime_defaults():
    from interactors.api.settings import Settings
    s = Settings(_env_file=None)
    assert s.agent_runtime == "auto"
    assert s.agent_model == "claude-sonnet-4-6"
    assert s.claude_max_turns == 30
    assert s.anthropic_api_key is None


def test_secret_key_defaults_none():
    from interactors.api.settings import Settings
    assert Settings(_env_file=None).secret_key is None


def test_model_gateway_defaults():
    from interactors.api.settings import Settings
    s = Settings(_env_file=None)
    assert s.model_gateway == "auto"
    assert s.litellm_base_url is None and s.litellm_api_key is None
