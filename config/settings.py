from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./data/traffic.db"
    PROXY_PORT: int = 8080
    API_PORT: int = 8000
    API_HOST: str = "0.0.0.0"
    SECRET_KEY: str = "change-me"
    DEFAULT_TIMEZONE: str = "UTC"
    CATEGORY_CACHE_TTL: int = 30
    IP_CACHE_TTL: int = 60
    WRITER_BATCH_SIZE: int = 100
    WRITER_FLUSH_INTERVAL: float = 0.2
    MITMPROXY_CA_DIR: str = "data/mitmproxy-ca"

    model_config = {"env_file": ".env"}


settings = Settings()
