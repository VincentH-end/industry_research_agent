from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "行业洞察 Agent"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4.1-mini"
    tavily_api_key: str = ""
    anchor_domains: str = "stats.gov.cn,worldbank.org,oecd.org"
    methodology_urls: str = ""
    max_sources: int = Field(default=8, ge=1, le=20)
    request_timeout_seconds: float = Field(default=15, ge=3, le=60)
    max_source_chars: int = Field(default=12000, ge=1000, le=50000)
    allow_private_networks: bool = False
    app_env: str = "dev"
    api_keys: str = ""
    log_level: str = "INFO"
    log_file: str = "logs/industry-agent.jsonl"
    server_host: str = "127.0.0.1"
    server_port: int = Field(default=8010, ge=1, le=65535)
    server_reload: bool = False
    server_auto_port: bool = True
    memory_db: str = "data/memory.sqlite3"
    memory_ttl_days: int = Field(default=30, ge=1, le=365)
    context_max_chars: int = Field(default=6000, ge=500, le=20000)
    prompt_max_chars: int = Field(default=50000, ge=5000, le=100000)
    eval_artifact_dir: str = "eval_results"
    rag_db: str = "data/reports.sqlite3"
    rag_max_age_days: int = Field(default=30, ge=1, le=3650)
    rag_top_k: int = Field(default=4, ge=1, le=10)

    @property
    def demo_mode(self) -> bool:
        return not bool(self.llm_api_key)

    @property
    def anchor_domain_list(self) -> list[str]:
        return [item.strip() for item in self.anchor_domains.split(",") if item.strip()]

    @property
    def methodology_url_list(self) -> list[str]:
        return [item.strip() for item in self.methodology_urls.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
