from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Postgres / TimescaleDB
    database_url: str = "postgresql+asyncpg://iot_admin:password@localhost:5432/iot_platform"

    # MQTT
    mqtt_broker_host: str = "localhost"
    mqtt_broker_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_client_id: str = "iot-worker"
    mqtt_telemetry_topic: str = "phy/+/telemetry"
    mqtt_status_topic: str = "phy/+/status"
    mqtt_keepalive: int = 60
    mqtt_reconnect_min_delay: int = 1
    mqtt_reconnect_max_delay: int = 30

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_secret_key: str = "dev-secret-change-me"
    api_access_token_expire_minutes: int = 60
    environment: str = "development"
    log_level: str = "INFO"

    # Rate limiting
    rate_limit_per_minute: int = 120

    # Alarm notification channels (Phase 6)
    alarm_webhook_url: str | None = None
    alarm_slack_webhook_url: str | None = None
    alarm_smtp_host: str | None = None
    alarm_smtp_port: int = 587
    alarm_email_from: str | None = None
    alarm_email_to: str = ""  # comma-separated
    device_offline_check_interval_seconds: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
