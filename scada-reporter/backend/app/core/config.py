from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET = "dev-secret-key-change-in-production"  # noqa: S105


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: str = "development"  # development | production
    DATABASE_URL: str = "postgresql+asyncpg://scada:scada123@localhost:5432/scada_reporter"
    SECRET_KEY: str = DEFAULT_SECRET
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # Virgülle ayrılmış izinli origin listesi (prod'da gerçek alan adlarıyla doldur)
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # DB bağlantı havuzu (postgres); sqlite'da yok sayılır
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # Collector (poller + OPC UA) bu process'te çalışsın mı? API'yi collector'dan
    # ayırmak için: API worker'larında False, ayrı collector process'inde True.
    RUN_COLLECTOR: bool = True

    S7_HOST: str = "192.168.112.50"
    S7_RACK: int = 0
    S7_SLOT: int = 1
    S7_POLL_INTERVAL: int = 5  # saniye (poller tick alt sınırı)
    S7_READ_TIMEOUT: int = 3  # saniye (tag ekleme anlık okuma zaman aşımı)
    S7_MAX_WORKERS: int = 32  # snap7 executor thread sayısı (>= PLC sayısı olmalı)
    S7_PLC_READ_TIMEOUT: float = 10.0  # saniye, tek PLC grup okuma üst sınırı
    # Deadband içinde kalan tag bile bu süre geçince zorla yazılır (heartbeat)
    S7_STORE_HEARTBEAT_SECONDS: int = 300
    # Ham hypertable saklama süresi (gün); rollup'lar daha uzun tutulabilir
    RAW_RETENTION_DAYS: int = 90

    # Dahili OPC UA server
    OPCUA_SERVER_PORT: int = 4840
    OPCUA_SERVER_URI: str = "http://scada-reporter.local/opcua"
    OPCUA_SERVER_UPDATE_INTERVAL: int = 2  # saniye

    REDIS_URL: str = "redis://localhost:6379/0"

    SENTRY_DSN: str = ""

    FACILITY_NAME: str = "Su/Atıksu Tesisi"
    REPORT_ARCHIVE_KEEP_DAYS: int = 365
    # Rapor gün sınırı için yerel saat ofseti (UTC+3 İstanbul). Günlük
    # toplamalar bu ofsetle kaydırılmış tarihe göre gruplanır.
    REPORT_TZ_OFFSET_HOURS: int = 3

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    def config_errors(self) -> list[str]:
        """Prod'da tehlikeli/eksik ayarları döndür (boşsa sağlıklı)."""
        errs: list[str] = []
        if not self.is_production:
            return errs

        # SECRET_KEY kontrolü (mevcut)
        if self.SECRET_KEY == DEFAULT_SECRET:
            errs.append("SECRET_KEY varsayılan değerde — production'da değiştirin.")

        # DATABASE_URL kontrolü: demo parola veya yerel bağlantı
        if (
            "scada123" in self.DATABASE_URL
            or "@localhost" in self.DATABASE_URL
            or "@127.0.0.1" in self.DATABASE_URL
        ):
            errs.append(
                "DATABASE_URL yerel/demo değerde — production'da gerçek sunucu ve"
                " güçlü parola kullanın."
            )

        # CORS kontrolü: boş, wildcard veya tümü localhost/127.0.0.1
        origins = self.cors_origins
        cors_unsafe = (
            len(origins) == 0
            or any(o == "*" for o in origins)
            or (len(origins) > 0 and all("localhost" in o or "127.0.0.1" in o for o in origins))
        )
        if cors_unsafe:
            errs.append(
                "CORS_ORIGINS güvensiz (boş, wildcard veya tümü localhost) —"
                " production'da gerçek alan adı girin."
            )

        return errs

    def config_warnings(self) -> list[str]:
        """Prod'da önerilen ama zorunlu olmayan ayarları döndür (boşsa sağlıklı)."""
        warnings: list[str] = []
        if self.is_production and self.RUN_COLLECTOR:
            warnings.append(
                "RUN_COLLECTOR=True — bu bir API process'iyse collector'ı ayırın"
                " (RUN_COLLECTOR=False)."
            )
        return warnings


settings = Settings()
