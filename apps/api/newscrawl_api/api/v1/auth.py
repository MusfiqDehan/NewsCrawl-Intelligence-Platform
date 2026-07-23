"""Authentication endpoints."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from newscrawl_api.api.deps import CurrentUser, DbDep, RedisDep, SettingsDep
from newscrawl_api.models import User
from newscrawl_api.schemas.auth import LoginRequest, TokenResponse, UserResponse
from newscrawl_api.services.auth import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

_MAX_LOGIN_ATTEMPTS = 10
_LOGIN_WINDOW_SECONDS = 300


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
    token = create_access_token(settings, user_id=user.id, email=user.email, role=user.role)
    return TokenResponse(
        access_token=token, expires_in_minutes=settings.jwt_access_token_expire_minutes
    )


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)
