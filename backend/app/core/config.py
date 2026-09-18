from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str
    google_api_key: str = ""
    murf_api_key: str = ""
    assemblyai_api_key: str = ""
    jwt_secret: str = ""
    jwt_expire_minutes: int = 60


settings = Settings()
