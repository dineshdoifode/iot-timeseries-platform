"""
Password hashing (bcrypt, used directly rather than via passlib — passlib
1.7.4 has a known compatibility bug with bcrypt>=4.1) and JWT access tokens.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config.settings import get_settings

settings = get_settings()

JWT_ALGORITHM = "HS256"


def hash_password(plain_password: str) -> str:
    # bcrypt has a 72-byte input limit; encode + truncate defensively.
    pw_bytes = plain_password.encode("utf-8")[:72]
    return bcrypt.hashpw(pw_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    pw_bytes = plain_password.encode("utf-8")[:72]
    try:
        return bcrypt.checkpw(pw_bytes, hashed_password.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(subject: str, role: str, expires_minutes: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.api_access_token_expire_minutes
    )
    payload = {"sub": subject, "role": role, "exp": expire, "iat": datetime.now(timezone.utc)}
    return jwt.encode(payload, settings.api_secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Raises jwt.PyJWTError on invalid/expired token — caller converts to 401."""
    return jwt.decode(token, settings.api_secret_key, algorithms=[JWT_ALGORITHM])


def generate_api_key() -> tuple[str, str]:
    """Returns (raw_key_to_show_once, sha256_hash_to_store)."""
    raw_key = f"iotk_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    return raw_key, key_hash


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
