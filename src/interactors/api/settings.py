from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="YAAH_", env_file=".env")

    profile: Literal["local", "remote"] = "local"
    auth_mode: Literal["dev", "auth0"] = "dev"
    database_url: str = "postgresql+psycopg://yaah:yaah@localhost:5433/yaah"
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    task_queue: str = "yaah-runs"

    github_app_id: str | None = None
    github_private_key: str | None = None      # PEM contents or a file path
    github_installation_id: str | None = None
    github_repo: str | None = None             # "owner/name" for the PR API
    github_base_branch: str = "main"

    anthropic_api_key: str | None = None
    agent_model: str = "claude-sonnet-4-6"
    claude_max_turns: int = 30
    agent_runtime: Literal["auto", "fake", "claude_code"] = "auto"

    secret_key: str | None = None
