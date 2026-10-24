from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
    )

    database_url: str | None = None
    database_host: str = "localhost"
    database_port: int = Field(default=5433, ge=1, le=65535)
    database_name: str = "humanitarian"
    database_user: str = "humanitarian"
    database_password: SecretStr | None = None
    world_bank_countries: str = (
        "ARG,AUS,BRA,DEU,FRA,GBR,ITA,JPN,KOR,MEX,RUS,SAU,TUR,USA,ZAF,JOR,KEN"
    )
    world_bank_indicators: str = (
        "SE.PRM.ENRR,SE.SEC.ENRR,SE.XPD.TOTL.GD.ZS,IT.NET.USER.ZS,SP.POP.TOTL"
    )
    world_bank_start_year: int = 2018
    world_bank_end_year: int = 2025
    unicef_indicators: str = (
        "ED_SE_LPV_PRIM,ED_SE_LPV_PRIM_LD,ED_SE_LPV_PRIM_SD"
    )
    unicef_start_year: int = 2018
    unicef_end_year: int = 2025
    http_timeout_seconds: float = Field(default=30, gt=0)
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-6-luna"
    ai_generation_key: SecretStr | None = None
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    mcp_api_base_url: str = "http://127.0.0.1:8000"

    @property
    def countries(self) -> tuple[str, ...]:
        return _csv_values(self.world_bank_countries)

    @property
    def indicators(self) -> tuple[str, ...]:
        return _csv_values(self.world_bank_indicators)

    @property
    def unicef_indicator_codes(self) -> tuple[str, ...]:
        return _csv_values(self.unicef_indicators)

    @property
    def allowed_origins(self) -> tuple[str, ...]:
        return _csv_values(self.cors_origins)

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        password = ""
        if self.database_password is not None:
            password = f":{quote(self.database_password.get_secret_value(), safe='')}"
        return (
            f"postgresql://{quote(self.database_user, safe='')}{password}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
            "?sslmode=require"
        )


def _csv_values(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()

