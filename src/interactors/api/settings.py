from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_storage_dir() -> str:
    """Absolute, outside any git repo. Agent workspaces nest under this base; a cwd-relative
    default would land inside whatever repo the worker runs from, letting an agent walk up the
    tree and edit the enclosing repo. Override with YAAH_STORAGE_DIR (e.g. the Docker volume)."""
    return str(Path.home() / ".yaah" / "workspaces")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="YAAH_", env_file=".env")

    profile: Literal["local", "remote"] = "local"
    auth_mode: Literal["dev", "auth0"] = "dev"
    database_url: str = "postgresql+psycopg://yaah:yaah@localhost:5433/yaah"
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    task_queue: str = "yaah-runs"
    storage_dir: str = Field(default_factory=_default_storage_dir)
    max_attachment_bytes: int = 10 * 1024 * 1024

    github_token: str | None = None            # PAT; preferred over the GitHub App when set
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

    litellm_base_url: str | None = None
    litellm_api_key: str | None = None
    model_gateway: Literal["anthropic", "litellm", "auto"] = "auto"
