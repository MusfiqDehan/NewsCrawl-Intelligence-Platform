"""Password hashing (argon2id) and JWT issuing/verification."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from newscrawl_contracts.enums import UserRole

from newscrawl_api.config import Settings

_hasher = PasswordHasher()


class AuthError(Exception):
    """Raised for any authentication failure (invalid credentials/token)."""


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def create_access_token(
    settings: Settings, *, user_id: uuid.UUID, email: str, role: UserRole
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role.value,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(settings: Settings, token: str) -> dict[str, str]:
    try:
        payload: dict[str, str] = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError as exc:
        raise AuthError("Invalid or expired token") from exc
    if "sub" not in payload or "role" not in payload:
        raise AuthError("Malformed token payload")
    return payload
