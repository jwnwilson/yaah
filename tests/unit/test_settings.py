from interactors.api.settings import Settings


def test_settings_defaults_to_local_dev():
    s = Settings(_env_file=None)
    assert s.profile == "local"
    assert s.auth_mode == "dev"
    assert s.database_url.startswith("postgresql+psycopg://")


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
