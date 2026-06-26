from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./data/traffic.db"
    PROXY_PORT: int = 8080
    API_PORT: int = 8000
    API_HOST: str = "0.0.0.0"
    SECRET_KEY: str = "change-me"
    # Dashboard login (HTTP Basic). Change ADMIN_PASSWORD before deploying.
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "change-me"
    AUTH_ENABLED: bool = True
    DEFAULT_TIMEZONE: str = "UTC"
    CATEGORY_CACHE_TTL: int = 30
    IP_CACHE_TTL: int = 60
    WRITER_BATCH_SIZE: int = 100
    WRITER_FLUSH_INTERVAL: float = 0.2
    MITMPROXY_CA_DIR: str = "data/mitmproxy-ca"

    model_config = {"env_file": ".env"}


settings = Settings()
