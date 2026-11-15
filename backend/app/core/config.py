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
    admin_token: str = ""          # proteção administrativa mínima (obrigatório; >= 12 caracteres)
    credentials_key: str = ""      # chave Fernet para criptografar credenciais de provedores
    lab_month_limit_usd: float = 10.0  # teto mensal de gastos do Laboratório


settings = Settings()
