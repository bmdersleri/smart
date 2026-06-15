from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://scada:scada123@localhost:5432/scada_reporter"
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    S7_HOST: str = "192.168.112.50"
    S7_RACK: int = 0
    S7_SLOT: int = 1
    S7_POLL_INTERVAL: int = 5  # saniye

    # Dahili OPC UA server
    OPCUA_SERVER_PORT: int = 4840
    OPCUA_SERVER_URI: str = "http://scada-reporter.local/opcua"
    OPCUA_SERVER_UPDATE_INTERVAL: int = 2  # saniye

    REDIS_URL: str = "redis://localhost:6379/0"

    SENTRY_DSN: str = ""

    FACILITY_NAME: str = "Su/Atıksu Tesisi"
    REPORT_ARCHIVE_KEEP_DAYS: int = 365


settings = Settings()
