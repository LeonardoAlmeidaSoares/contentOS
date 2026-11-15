from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://contentos:contentos_dev_pw@localhost:5432/contentos"
    redis_url: str = "redis://localhost:6379/0"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "contentos"
    minio_secret_key: str = "contentos_dev_pw"
    minio_bucket: str = "contentos-artifacts"
    minio_secure: bool = False
    stale_run_minutes: int = 15


settings = Settings()
