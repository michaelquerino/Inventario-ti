from datetime import datetime, timedelta, timezone
import binascii
from hashlib import pbkdf2_hmac
from hmac import compare_digest
import base64
import secrets

import jwt

from app.core.config import settings

_PBKDF2_ITERATIONS = 210_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    payload = base64.b64encode(salt + digest).decode("utf-8")
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${payload}"


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        scheme, iterations_text, payload = hashed_password.split("$", 2)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        decoded = base64.b64decode(payload.encode("utf-8"))
        salt = decoded[:16]
        expected = decoded[16:]
        actual = pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return compare_digest(actual, expected)
    except (ValueError, TypeError, binascii.Error):
        return False


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
