from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # App
    app_name: str = "Dev Agent Platform"
    debug: bool = False

    # GitHub
    github_token: Optional[str] = None

    # LLM
    anthropic_api_key: Optional[str] = None
    llm_model: str = "claude-sonnet-4-20250514"

    # Storage
    repos_base_path: str = "/tmp/dev-agent-repos"

    # Agent timeouts (seconds)
    agent_timeout: int = 300

    class Config:
        env_file = ".env"


settings = Settings()
