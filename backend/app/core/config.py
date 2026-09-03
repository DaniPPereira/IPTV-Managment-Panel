from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://iptv:CHANGE_ME@postgres:5432/iptv"
    app_secret_key: str = "CHANGE_ME"
    data_encryption_key: str = "CHANGE_ME"

    admin_username: str = "admin"
    admin_initial_password: str = "CHANGE_ME"

    public_base_url: str = "http://localhost"
    access_log_retention_days: int = 30

    m3u_cache_seconds: int = 300
    epg_cache_seconds: int = 3600

    cache_dir: str = "/app/cache"
    allow_private_urls: bool = False
    setup_page_enabled: bool = True

    jwt_cookie_name: str = "iptv_admin_token"
    jwt_expire_hours: int = 12
    cookie_secure: bool = False
    cookie_samesite: str = "lax"

    http_timeout_seconds: float = 15.0
    http_max_bytes: int = 50 * 1024 * 1024
    http_max_redirects: int = 3

    expiring_soon_days: int = 7

    rate_limit_public_per_minute: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
