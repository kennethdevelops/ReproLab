"""Runtime configuration loaded from environment variables.

Only non-secret values are ever exposed through the API (see ``public_view``).
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class AppMode(StrEnum):
    LOCAL = "local"
    PUBLIC_DEMO = "public_demo"


def _split_csv(value: object) -> object:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    app_mode: AppMode = AppMode.LOCAL
    api_base_url: str = "http://localhost:8000"
    web_base_url: str = "http://localhost:3000"
    database_url: str = "postgresql+psycopg://reprolab:reprolab@localhost:5432/reprolab"
    redis_url: str = "redis://localhost:6379/0"
    artifacts_dir: Path = Path("./data/artifacts")
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    llm_provider: str = "anthropic"
    llm_model: str = "claude-opus-5-5"
    llm_effort: str = "medium"
    llm_max_tokens_per_call: int = 8000
    # Server-side refusal fallback (Anthropic beta). Disable only if the account lacks access.
    llm_refusal_fallback: bool = True
    anthropic_api_key: SecretStr | None = None

    embedding_provider: str = "fastembed"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_cache_dir: Path | None = None

    # Operator-exported local snapshots (`python -m reprolab.indexing.local_snapshot export`).
    snapshots_dir: Path = Path("./data/snapshots")
    github_api_url: str = "https://api.github.com"
    max_index_files: int = 2000
    max_index_file_bytes: int = 200_000
    max_index_chunks: int = 20_000
    retrieval_top_k: int = 6
    retrieval_candidates: int = 30
    retrieval_rrf_k: int = 60

    max_browser_steps: int = 25
    max_retrieval_calls: int = 10
    max_investigation_seconds: int = 300
    max_model_calls: int = 30
    max_input_tokens_per_run: int = 400_000
    max_output_tokens_per_run: int = 40_000
    max_run_cost_usd: float = 1.00
    max_concurrent_investigations: int = 1
    max_queued_investigations: int = 10
    max_bug_report_chars: int = 4000
    public_demo_daily_cost_cap_usd: float = 2.00

    public_demo_enabled: bool = False
    demo_allowed_origin: str = "http://demo-target:4173"
    # Fixed-variant fixture, used only by test validation and evaluation; never an agent target.
    demo_fixed_origin: str = "http://demo-target-fixed:4173"
    local_extra_allowed_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    github_public_repo_enabled: bool = True
    allow_private_repos: bool = False
    github_token: SecretStr | None = None

    demo_admin_token: SecretStr | None = None
    demo_cases_path: Path = Path("../benchmarks/cases/cases.v1.json")

    _split = field_validator("cors_allowed_origins", "local_extra_allowed_origins", mode="before")(
        _split_csv
    )

    @property
    def is_public_demo(self) -> bool:
        return self.app_mode is AppMode.PUBLIC_DEMO

    def public_view(self) -> dict[str, object]:
        """Settings safe to show in the UI. Never includes secrets."""
        return {
            "app_mode": self.app_mode.value,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "llm_configured": self.llm_provider == "stub"
            or (self.llm_provider == "anthropic" and self.anthropic_api_key is not None),
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
            "limits": {
                "max_browser_steps": self.max_browser_steps,
                "max_retrieval_calls": self.max_retrieval_calls,
                "max_investigation_seconds": self.max_investigation_seconds,
                "max_model_calls": self.max_model_calls,
                "max_run_cost_usd": self.max_run_cost_usd,
                "max_bug_report_chars": self.max_bug_report_chars,
            },
            "demo_allowed_origin": self.demo_allowed_origin,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
