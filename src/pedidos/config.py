"""Settings read from environment variables or from the .env file (see .env.example)."""

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_path: Path = Path("data/pedidos.db")
    # SecretStr keeps the key out of logs and error messages.
    gemini_api_key: SecretStr = SecretStr("")
    llm_model: str = "gemini-3.5-flash-lite"
    llm_timeout_s: float = 20.0
