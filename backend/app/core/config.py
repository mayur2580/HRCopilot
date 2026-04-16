from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "HR Multi-Agent Backend"
    app_env: str = Field(default="development")
    api_prefix: str = "/api"
    cors_origins: str = Field(default="http://localhost:5173,http://127.0.0.1:5173")
    auto_ensure_index: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
