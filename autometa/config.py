from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentStage(StrEnum):
    PROTOCOL = "protocol"
    SEARCH = "search"
    SCREENING = "screening"
    EXTRACTION = "extraction"
    META_ANALYSIS = "meta_analysis"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_api_key: SecretStr = SecretStr("")
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = ""
    protocol_model: str = ""
    search_model: str = ""
    screening_model: str = ""
    extraction_model: str = ""
    meta_analysis_model: str = ""
    pubmed_api_key: SecretStr = SecretStr("")
    autometa_data_dir: Path = Path("data")
    autometa_host: str = "127.0.0.1"
    autometa_port: int = Field(default=8016, ge=1, le=65535)

    def model_for(self, stage: AgentStage) -> str:
        override = {
            AgentStage.PROTOCOL: self.protocol_model,
            AgentStage.SEARCH: self.search_model,
            AgentStage.SCREENING: self.screening_model,
            AgentStage.EXTRACTION: self.extraction_model,
            AgentStage.META_ANALYSIS: self.meta_analysis_model,
        }[stage]
        return override or self.llm_model

    def safe_summary(self) -> dict[str, object]:
        return {
            "base_url": self.llm_base_url,
            "default_model": self.llm_model,
            "data_dir": str(self.autometa_data_dir),
            "host": self.autometa_host,
            "port": self.autometa_port,
            "api_key_configured": bool(self.llm_api_key.get_secret_value()),
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
