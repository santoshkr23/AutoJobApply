"""Password hashing, token generation and password policy."""

import hashlib
import hmac
import re
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()  # argon2id with library defaults

# Precomputed so login timing does not reveal whether an account exists.
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")

COMMON_PASSWORDS = {
    "password", "password1", "password123", "123456789", "12345678", "qwertyuiop",
    "iloveyou123", "admin12345", "welcome123", "letmein123",
}


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-ish time verification; also burns a hash when the account has no password."""
    if not password_hash:
        try:
            _hasher.verify(_DUMMY_HASH, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            pass
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def validate_password_strength(password: str) -> list[str]:
    problems: list[str] = []
    if len(password) < 10:
        problems.append("Password must be at least 10 characters long.")
    if len(password) > 128:
        problems.append("Password must be at most 128 characters long.")
    if password.lower() in COMMON_PASSWORDS:
        problems.append("Password is too common.")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        problems.append("Password must contain both letters and numbers.")
    return problems


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
