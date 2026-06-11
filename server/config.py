"""Runtime config — env-driven so the same image can point at staging or prod."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Claude Code spawns the MCP server with its own CWD, so a relative .env path
# won't find ours. Resolve to the repo root absolutely.
_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_PATH), extra="ignore")

    # Empty defaults force the operator to point at their own deployment.
    # We don't want a real URL in the source so a forked clone can't
    # accidentally call someone else's instance.
    oci_api_url: str = Field(default="", alias="OCI_API_URL")
    oci_api_key: str = Field(default="", alias="OCI_API_KEY")
    oci_timeout_s: float = Field(default=30.0, alias="OCI_TIMEOUT_S")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @property
    def base(self) -> str:
        return self.oci_api_url.rstrip("/")


settings = Settings()
