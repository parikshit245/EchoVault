from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "EchoVault Node Service"
    app_env: str = "development"
    host: str = "0.0.0.0"
    node_host: str = "localhost"
    port: int = 8000
    grpc_host: str = "localhost"
    grpc_bind_host: str = "0.0.0.0"
    grpc_port: int = 50051
    grpc_timeout_seconds: float = 5.0
    database_url: str = ""
    node_id: str = "node-dev-001"
    node_name: str = "Development Node"
    node_type: str = "coordinator"
    frontend_origin: str = "http://localhost:3000"
    storage_dir: str = "storage/evidence"
    max_upload_size_mb: int = 50

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
