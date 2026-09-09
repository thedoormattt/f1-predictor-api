from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    supabase_url: str
    supabase_service_key: str
    supabase_anon_key: str
    secret_key: str = "dev-secret"
    environment: str = "development"

    # ── Automatic post-race scoring ──────────────────────────
    autoscore_enabled: bool = True
    # How often the background sweep runs.
    autoscore_interval_minutes: int = 15
    # How long after lights out a session is treated as finished. Gives OpenF1
    # time to publish final classification, laps, pitstops and race control.
    autoscore_race_delay_minutes: int = 210      # 3h30
    autoscore_sprint_delay_minutes: int = 120    # 2h
    # Races older than this are left alone (rescore manually if ever needed).
    autoscore_lookback_days: int = 10

    class Config:
        env_file = ".env"


settings = Settings()
