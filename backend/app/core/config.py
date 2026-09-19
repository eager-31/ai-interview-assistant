from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str
    google_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    murf_api_key: str = ""
    assemblyai_api_key: str = ""
    jwt_secret: str = Field(min_length=32)
    jwt_expire_minutes: int = 60
    submit_answer_rate_limit: str = "10/minute"


settings = Settings()
