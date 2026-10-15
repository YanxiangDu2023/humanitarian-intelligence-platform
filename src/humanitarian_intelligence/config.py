from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql://humanitarian:humanitarian@localhost:5433/humanitarian"
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

    @property
    def countries(self) -> tuple[str, ...]:
        return _csv_values(self.world_bank_countries)

    @property
    def indicators(self) -> tuple[str, ...]:
        return _csv_values(self.world_bank_indicators)

    @property
    def unicef_indicator_codes(self) -> tuple[str, ...]:
        return _csv_values(self.unicef_indicators)


def _csv_values(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()

