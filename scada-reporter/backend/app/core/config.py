from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://scada:scada123@localhost:5432/scada_reporter"
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    OPC_UA_URL: str = "opc.tcp://localhost:49320"
    OPC_UA_USERNAME: str = ""
    OPC_UA_PASSWORD: str = ""
    OPC_UA_POLL_INTERVAL: int = 5  # saniye

    REDIS_URL: str = "redis://localhost:6379/0"


settings = Settings()
