"""
app/config.py
Application settings, loaded from environment variables (.env file).
Centralised here so every other file imports from one place.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ---- Core ----
    app_name: str = "Timesheet AI"
    secret_key: str = "dev-secret-change-me"
    database_url: str = "sqlite:///./data/timesheet.db"

    # ---- AI ----
    gemini_api_key: str = "" # Free-tier friendly
    gemini_model: str = "gemini-flash-lite-latest"
    # ---- Behaviour tuning ----
    overload_threshold: float = 1.35   # 35% over team average = overloaded
    burnout_daily_hours: float = 10.0  # > this many hours/day = potential burnout

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
