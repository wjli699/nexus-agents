"""Runtime configuration, read from environment variables.

Values mirror the Postgres service in docker/docker-compose.yml. Locally you
can export them or drop them in nexus-backend/.env (gitignored); in Docker
they come from the compose `environment:` block.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Postgres (same instance n8n uses) ---
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_user: str = "nexus"
    postgres_password: str = ""
    postgres_db: str = "nexus"

    # --- LLM endpoint for intent classification ---
    # Local Ollama by default; see README "Local LLM vs Claude API".
    # Reasoning models need "think": false in the body (JOURNAL.md #10).
    llm_base_url: str = "http://localhost:11434"
    llm_model: str = "qwen3.5:9b"

    # --- External APIs ---
    alpha_vantage_api_key: str = ""

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
