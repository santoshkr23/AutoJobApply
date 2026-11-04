"""Field-level encryption (Fernet) for sensitive stored values such as phone numbers."""

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.core.config import get_settings

_PREFIX = "enc:v1:"


@lru_cache
def _fernet() -> Fernet:
    s = get_settings()
    if s.encryption_key:
        return Fernet(s.encryption_key.encode())
    if s.is_production_like:
        raise RuntimeError("ENCRYPTION_KEY must be set in staging/production")
    # Development only: derive a stable key from SECRET_KEY so local data stays readable.
    digest = hashlib.sha256(("dev-fernet:" + s.secret_key).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str) -> str:
    return _PREFIX + _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    if not value.startswith(_PREFIX):
        return value  # legacy/plaintext rows written before encryption was enabled
    try:
        return _fernet().decrypt(value[len(_PREFIX):].encode()).decode()
    except InvalidToken as exc:  # wrong key or corrupted data
        raise ValueError("Unable to decrypt stored value") from exc


class EncryptedText(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else encrypt(value)

    def process_result_value(self, value, dialect):
        return None if value is None else decrypt(value)
