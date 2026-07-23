"""Source configuration management."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from newscrawl_api.api.deps import AdminUser, CurrentUser, DbDep
from newscrawl_api.models import Source
from newscrawl_api.schemas.source import SourceCreate, SourceResponse, SourceUpdate

router = APIRouter(prefix="/sources", tags=["sources"])


async def _get_source_or_404(db: DbDep, source_id: uuid.UUID) -> Source:
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return source


@router.get("", response_model=list[SourceResponse])
async def list_sources(db: DbDep, _user: CurrentUser) -> list[SourceResponse]:
    sources = (await db.scalars(select(Source).order_by(Source.name))).all()
    return [SourceResponse.model_validate(s) for s in sources]


@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def create_source(payload: SourceCreate, db: DbDep, _admin: AdminUser) -> SourceResponse:
    existing = await db.scalar(select(Source).where(Source.slug == payload.slug))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Source with slug '{payload.slug}' already exists",
        )
    source = Source(**payload.model_dump())
    db.add(source)
    await db.flush()
    await db.refresh(source)
    return SourceResponse.model_validate(source)


@router.get("/{source_id}", response_model=SourceResponse)
async def get_source(
    db: DbDep, _user: CurrentUser, source: Source = Depends(_get_source_or_404)
) -> SourceResponse:
    return SourceResponse.model_validate(source)


@router.patch("/{source_id}", response_model=SourceResponse)
async def update_source(
    payload: SourceUpdate,
    db: DbDep,
    _admin: AdminUser,
    source: Source = Depends(_get_source_or_404),
) -> SourceResponse:
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(source, field, value)
    await db.flush()
    await db.refresh(source)
    return SourceResponse.model_validate(source)
