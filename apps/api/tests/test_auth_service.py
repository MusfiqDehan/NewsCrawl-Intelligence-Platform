import uuid

import pytest
from newscrawl_api.config import Settings
from newscrawl_api.services.auth import (
    AuthError,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from newscrawl_contracts.enums import UserRole


def make_settings(**overrides: object) -> Settings:
    return Settings(jwt_secret_key="test-secret-0123456789abcdef0123456789abcdef", **overrides)  # type: ignore[arg-type]


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("s3cret-пароль-গোপন")
    assert hashed != "s3cret-пароль-গোপন"
    assert verify_password("s3cret-пароль-গোপন", hashed)
    assert not verify_password("wrong", hashed)


def test_token_roundtrip() -> None:
    settings = make_settings()
    user_id = uuid.uuid4()
    token = create_access_token(settings, user_id=user_id, email="a@b.com", role=UserRole.ADMIN)
    payload = decode_access_token(settings, token)
    assert payload["sub"] == str(user_id)
    assert payload["role"] == "admin"
    assert payload["typ"] == "access"


def test_refresh_token_roundtrip() -> None:
    settings = make_settings()
    user_id = uuid.uuid4()
    token, jti = create_refresh_token(settings, user_id=user_id)
    payload = decode_refresh_token(settings, token)
    assert payload["sub"] == str(user_id)
    assert payload["jti"] == jti
    assert payload["typ"] == "refresh"


def test_refresh_token_rejected_as_access() -> None:
    settings = make_settings()
    token, _ = create_refresh_token(settings, user_id=uuid.uuid4())
    with pytest.raises(AuthError, match="Invalid token type"):
        decode_access_token(settings, token)


def test_access_token_rejected_as_refresh() -> None:
    settings = make_settings()
    token = create_access_token(
        settings, user_id=uuid.uuid4(), email="a@b.com", role=UserRole.VIEWER
    )
    with pytest.raises(AuthError, match="Invalid token type"):
        decode_refresh_token(settings, token)


def test_tampered_token_rejected() -> None:
    settings = make_settings()
    token = create_access_token(
        settings, user_id=uuid.uuid4(), email="a@b.com", role=UserRole.VIEWER
    )
    with pytest.raises(AuthError):
        decode_access_token(settings, token + "x")


def test_token_wrong_secret_rejected() -> None:
    token = create_access_token(
        make_settings(), user_id=uuid.uuid4(), email="a@b.com", role=UserRole.VIEWER
    )
    other = Settings(jwt_secret_key="other-secret-0123456789abcdef0123456789abcdef")
    with pytest.raises(AuthError):
        decode_access_token(other, token)


def test_expired_token_rejected() -> None:
    settings = make_settings(jwt_access_token_expire_minutes=-1)
    token = create_access_token(
        settings, user_id=uuid.uuid4(), email="a@b.com", role=UserRole.VIEWER
    )
    with pytest.raises(AuthError):
        decode_access_token(settings, token)
