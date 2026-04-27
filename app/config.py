from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    supabase_url: str
    supabase_service_key: str
    supabase_anon_key: str
    secret_key: str = "dev-secret"
    environment: str = "development"

    class Config:
        env_file = ".env"


settings = Settings()
