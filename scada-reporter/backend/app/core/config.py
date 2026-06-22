from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET = "dev-secret-key-change-in-production"  # noqa: S105


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: str = "development"  # development | production
    DATABASE_URL: str = "postgresql+asyncpg://scada:scada123@localhost:5432/scada_reporter"
    SECRET_KEY: str = DEFAULT_SECRET
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    STREAM_TOKEN_TTL_SECONDS: int = 60

    # Virgülle ayrılmış izinli origin listesi (prod'da gerçek alan adlarıyla doldur)
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # DB bağlantı havuzu (postgres); sqlite'da yok sayılır
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # Collector (poller + OPC UA) bu process'te çalışsın mı? API'yi collector'dan
    # ayırmak için: API worker'larında False, ayrı collector process'inde True.
    RUN_COLLECTOR: bool = True

    # Başlangıçta Base.metadata.create_all() çağrılsın mı? Dev'de True (varsayılan)
    # yeterli; production'da False yapın — şema Alembic migration'larıyla yönetilir.
    AUTO_CREATE_TABLES: bool = True

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

    # Commercial license verification. Disabled by default so development and
    # tests remain frictionless; enable in production/on-prem deployments.
    SCADA_LICENSE_REQUIRED: bool = False
    SCADA_LICENSE_FILE: str = ""
    SCADA_LICENSE_TOKEN: str = ""
    SCADA_LICENSE_PUBLIC_KEY: str = ""
    SCADA_LICENSE_ALGORITHMS: str = "RS256,ES256"
    SCADA_LICENSE_PRODUCT: str = "ekont-smart-report"

    # ── Login rate limiting (brute-force koruması) ──
    LOGIN_RATE_LIMIT_ENABLED: bool = True
    LOGIN_RATE_LIMIT_MAX: int = 10  # pencere içinde max başarısız deneme
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 60  # pencere uzunluğu (saniye)

    FACILITY_NAME: str = "Su/Atıksu Tesisi"
    REPORT_ARCHIVE_KEEP_DAYS: int = 365
    # Rapor gün sınırı için yerel saat ofseti (UTC+3 İstanbul). Günlük
    # toplamalar bu ofsetle kaydırılmış tarihe göre gruplanır.
    REPORT_TZ_OFFSET_HOURS: int = 3

    # ── PLC sağlık izleme ──
    PLC_MONITOR_INTERVAL: int = 10  # monitor değerlendirme periyodu (sn)
    PLC_STALE_SECONDS: float = 60.0  # bağlı ama bu süre GOOD okuma yoksa stale
    PLC_PARTIAL_BAD_RATIO: float = 0.5  # tick BAD oranı bu üstündeyse kısmi hata
    PLC_PARTIAL_BAD_CYCLES: int = 3  # kısmi hata için ardışık tick
    PLC_FLAP_WINDOW_SECONDS: float = 120.0  # flapping penceresi
    PLC_FLAP_COUNT: int = 3  # pencerede bu kadar reconnect = flapping
    PLC_RECOVER_CYCLES: int = 2  # auto-resolve için temiz tick (histerezis)
    PLC_INCIDENT_RETENTION_DAYS: int = 90  # resolved incident saklama

    # ── Uyarı kanalları (varsayılan kapalı) ──
    ALERT_MIN_SEVERITY: str = "warning"  # warning | critical (e-posta/webhook kapısı)
    ALERT_EMAIL_ENABLED: bool = False
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    ALERT_EMAIL_FROM: str = ""
    ALERT_EMAIL_TO: str = ""  # virgülle ayrılmış alıcılar
    ALERT_WEBHOOK_URL: str = ""

    GRAFANA_URL: str = "http://localhost:3000"
    GRAFANA_USER: str = "admin"
    # Dev default = yerel Grafana (admin123). Production'da .env ile override et;
    # config_warnings() admin/admin123'ü zaten zayıf-parola olarak uyarır.
    GRAFANA_PASSWORD: str = "admin123"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def scada_license_algorithms(self) -> list[str]:
        return [a.strip() for a in self.SCADA_LICENSE_ALGORITHMS.split(",") if a.strip()]

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
        if self.ALERT_EMAIL_ENABLED and not (self.SMTP_HOST and self.ALERT_EMAIL_TO):
            warnings.append(
                "ALERT_EMAIL_ENABLED=True ama SMTP_HOST/ALERT_EMAIL_TO eksik —"
                " e-posta uyarıları gönderilemez."
            )
        # Grafana zayıf/demo parola — opsiyonel entegrasyon, hard-stop değil (uyarı).
        if self.is_production and self.GRAFANA_PASSWORD in ("admin", "admin123"):
            warnings.append(
                "GRAFANA_PASSWORD zayıf/demo değerde — Grafana senkronu kullanıyorsanız"
                " production'da güçlü parola verin (yalnızca env üzerinden)."
            )
        return warnings


settings = Settings()
