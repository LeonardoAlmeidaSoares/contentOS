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
    gemini_api_key: str = ""       # chave da Gemini API (variável de ambiente GEMINI_API_KEY; nunca persistida)
    gemini_text_model: str = "gemini-3.1-flash-lite"  # modelo com camada gratuita; troque por env se necessário
    pexels_api_key: str = ""       # opcional: fonte de imagens (gratuita, requer chave)
    media_user_agent: str = "ContentOS/1.0 (internal studio)"
    tts_piper_model: str = "/opt/piper/pt_BR-faber-medium.onnx"

    youtube_client_id: str = ""      # cliente OAuth do tipo "App para computador" (Google Cloud)
    youtube_client_secret: str = ""
    youtube_redirect_uri: str = "http://127.0.0.1:8302/"  # loopback: nada escuta; o PO copia a URL do navegador


settings = Settings()
