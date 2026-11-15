"""Criptografia de credenciais em repouso (Fernet). A chave vem do ambiente, nunca do banco."""
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _fernet() -> Fernet:
    if not settings.credentials_key:
        raise RuntimeError("CREDENTIALS_KEY não configurada")
    return Fernet(settings.credentials_key.encode())


def encrypt(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        raise RuntimeError("não foi possível descriptografar a credencial (CREDENTIALS_KEY alterada?)") from None


def hint(plain: str) -> str:
    """Dica segura para a UI: nunca revela a credencial inteira."""
    return f"…{plain[-4:]}" if len(plain) >= 16 else "••••"
