"""API users (JWT auth with role-based permissions)."""

import uuid

from newscrawl_contracts.enums import UserRole
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from newscrawl_api.models.base import Base, TimestampMixin, str_enum, uuid_pk


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[UserRole] = mapped_column(str_enum(UserRole), default=UserRole.VIEWER)
    is_active: Mapped[bool] = mapped_column(default=True)
