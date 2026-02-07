"""Application settings loaded from environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuration for edinet-mcp.

    Values are read from environment variables or a `.env` file.
    """

    edinet_api_key: str = ""
    edinet_base_url: str = "https://api.edinet-fsa.go.jp/api/v2"
    cache_dir: Path = Path.home() / ".cache" / "edinet-mcp"
    rate_limit_rps: float = 0.5  # requests per second (conservative default)
    request_timeout: float = 30.0

    model_config = {"env_prefix": "", "env_file": ".env", "extra": "ignore"}


def get_settings(**overrides: object) -> Settings:
    """Create a Settings instance, allowing programmatic overrides."""
    return Settings(**overrides)  # type: ignore[arg-type]
