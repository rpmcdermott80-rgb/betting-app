from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://betting:changeme@localhost:5432/betting"
    anthropic_api_key: str = ""
    betfair_app_key: str = ""
    betfair_username: str = ""
    betfair_password: str = ""


settings = Settings()
