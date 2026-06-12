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
