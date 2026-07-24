"""Authentication endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from newscrawl_api.api.deps import CurrentUser, DbDep, RedisDep, SettingsDep
from newscrawl_api.config import Settings
from newscrawl_api.models import User
from newscrawl_api.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenResponse,
    UserResponse,
)
from newscrawl_api.services.auth import (
    AuthError,
    decode_refresh_token,
    issue_token_pair,
    refresh_token_is_active,
    revoke_refresh_token,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_MAX_LOGIN_ATTEMPTS = 10
_LOGIN_WINDOW_SECONDS = 300


def _token_response(settings: Settings, access_token: str, refresh_token: str) -> TokenResponse:
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in_minutes=settings.jwt_access_token_expire_minutes,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest, db: DbDep, redis: RedisDep, settings: SettingsDep
) -> TokenResponse:
    # Brute-force protection: fixed window per email.
    attempts_key = f"auth:attempts:{payload.email.lower()}"
    attempts = await redis.incr(attempts_key)
    if attempts == 1:
        await redis.expire(attempts_key, _LOGIN_WINDOW_SECONDS)
    if attempts > _MAX_LOGIN_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts; try again later",
        )

    user = await db.scalar(select(User).where(User.email == payload.email.lower()))
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    await redis.delete(attempts_key)
    access, refresh = await issue_token_pair(
        redis, settings, user_id=user.id, email=user.email, role=user.role
    )
    return _token_response(settings, access, refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest, db: DbDep, redis: RedisDep, settings: SettingsDep
) -> TokenResponse:
    try:
        claims = decode_refresh_token(settings, payload.refresh_token)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    user_id = uuid.UUID(str(claims["sub"]))
    jti = str(claims["jti"])
    if not await refresh_token_is_active(redis, jti=jti, user_id=user_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked"
        )

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        await revoke_refresh_token(redis, jti=jti)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive"
        )

    # Rotate: revoke the presented refresh token, then mint a fresh pair.
    await revoke_refresh_token(redis, jti=jti)
    access, new_refresh = await issue_token_pair(
        redis, settings, user_id=user.id, email=user.email, role=user.role
    )
    return _token_response(settings, access, new_refresh)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: LogoutRequest, redis: RedisDep, settings: SettingsDep
) -> None:
    try:
        claims = decode_refresh_token(settings, payload.refresh_token)
    except AuthError:
        # Idempotent logout: invalid/expired refresh tokens are treated as already gone.
        return
    await revoke_refresh_token(redis, jti=str(claims["jti"]))


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)
