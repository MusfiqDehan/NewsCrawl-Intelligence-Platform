"""Password hashing (argon2id) and JWT issuing/verification."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from newscrawl_contracts.enums import UserRole
from redis.asyncio import Redis

from newscrawl_api.config import Settings

_hasher = PasswordHasher()

_REFRESH_KEY_PREFIX = "auth:refresh:"


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
        "typ": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(settings: Settings, *, user_id: uuid.UUID) -> tuple[str, str]:
    """Return (token, jti). Caller must persist jti in Redis for revocation."""
    now = datetime.now(UTC)
    jti = str(uuid.uuid4())
    payload = {
        "sub": str(user_id),
        "typ": "refresh",
        "jti": jti,
        "iat": now,
        "exp": now + timedelta(days=settings.jwt_refresh_token_expire_days),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, jti


def decode_access_token(settings: Settings, token: str) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError as exc:
        raise AuthError("Invalid or expired token") from exc
    # Tokens minted before typ was added are treated as access tokens.
    if payload.get("typ", "access") != "access":
        raise AuthError("Invalid token type")
    if "sub" not in payload or "role" not in payload:
        raise AuthError("Malformed token payload")
    return payload


def decode_refresh_token(settings: Settings, token: str) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError as exc:
        raise AuthError("Invalid or expired refresh token") from exc
    if payload.get("typ") != "refresh":
        raise AuthError("Invalid token type")
    if "sub" not in payload or "jti" not in payload:
        raise AuthError("Malformed refresh token payload")
    return payload


def _refresh_redis_key(jti: str) -> str:
    return f"{_REFRESH_KEY_PREFIX}{jti}"


async def store_refresh_token(
    redis: Redis, settings: Settings, *, jti: str, user_id: uuid.UUID
) -> None:
    ttl = int(timedelta(days=settings.jwt_refresh_token_expire_days).total_seconds())
    await redis.set(_refresh_redis_key(jti), str(user_id), ex=ttl)


async def revoke_refresh_token(redis: Redis, *, jti: str) -> None:
    await redis.delete(_refresh_redis_key(jti))


async def refresh_token_is_active(redis: Redis, *, jti: str, user_id: uuid.UUID) -> bool:
    stored = await redis.get(_refresh_redis_key(jti))
    if stored is None:
        return False
    value = stored.decode() if isinstance(stored, bytes) else str(stored)
    return value == str(user_id)


async def issue_token_pair(
    redis: Redis,
    settings: Settings,
    *,
    user_id: uuid.UUID,
    email: str,
    role: UserRole,
) -> tuple[str, str]:
    access = create_access_token(settings, user_id=user_id, email=email, role=role)
    refresh, jti = create_refresh_token(settings, user_id=user_id)
    await store_refresh_token(redis, settings, jti=jti, user_id=user_id)
    return access, refresh
