"""Crawl job management endpoints.

Lifecycle actions publish a control signal on the Redis pub/sub channel so
running workers react without polling the database.
"""

import uuid

from fastapi import APIRouter, HTTPException, Query, status
from newscrawl_contracts.enums import CrawlJobStatus
from sqlalchemy import func, select

from newscrawl_api.api.deps import AdminUser, CurrentUser, DbDep, RedisDep
from newscrawl_api.coordination import ControlAction, ControlSignal
from newscrawl_api.coordination.control import publish_signal
from newscrawl_api.models import CrawlJob, Source
from newscrawl_api.schemas.crawl_job import (
    CrawlJobCreate,
    CrawlJobListResponse,
    CrawlJobResponse,
)
from newscrawl_api.services.crawl_jobs import (
    CrawlJobService,
    InvalidTransitionError,
    JobParamsError,
)

router = APIRouter(prefix="/crawl-jobs", tags=["crawl-jobs"])

service = CrawlJobService()


async def _get_job_or_404(db: DbDep, job_id: uuid.UUID) -> CrawlJob:
    job = await db.get(CrawlJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crawl job not found")
    return job


async def _publish_control(redis: RedisDep, action: ControlAction, job: CrawlJob) -> None:
    await publish_signal(
        redis, ControlSignal(action=action, job_id=job.id, source_id=job.source_id)
    )


@router.post("", response_model=CrawlJobResponse, status_code=status.HTTP_201_CREATED)
async def create_crawl_job(
    payload: CrawlJobCreate, db: DbDep, admin: AdminUser
) -> CrawlJobResponse:
    source = await db.get(Source, payload.source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    if not source.enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Source is disabled")
    try:
        job = await service.create_job(
            db,
            source,
            job_type=payload.job_type,
            params=payload.params,
            priority=payload.priority,
            created_by=admin.id,
        )
    except JobParamsError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    await db.flush()
    await db.refresh(job)
    return CrawlJobResponse.model_validate(job)


@router.get("", response_model=CrawlJobListResponse)
async def list_crawl_jobs(
    db: DbDep,
    _user: CurrentUser,
    source_id: uuid.UUID | None = None,
    job_status: CrawlJobStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> CrawlJobListResponse:
    query = select(CrawlJob)
    if source_id is not None:
        query = query.where(CrawlJob.source_id == source_id)
    if job_status is not None:
        query = query.where(CrawlJob.status == job_status)

    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    jobs = (
        await db.scalars(query.order_by(CrawlJob.created_at.desc()).limit(limit).offset(offset))
    ).all()
    return CrawlJobListResponse(
        items=[CrawlJobResponse.model_validate(j) for j in jobs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{job_id}", response_model=CrawlJobResponse)
async def get_crawl_job(db: DbDep, _user: CurrentUser, job_id: uuid.UUID) -> CrawlJobResponse:
    job = await _get_job_or_404(db, job_id)
    return CrawlJobResponse.model_validate(job)


def _transition_or_409(exc: InvalidTransitionError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post("/{job_id}/pause", response_model=CrawlJobResponse)
async def pause_crawl_job(
    db: DbDep, redis: RedisDep, _admin: AdminUser, job_id: uuid.UUID
) -> CrawlJobResponse:
    job = await _get_job_or_404(db, job_id)
    try:
        job = await service.pause(db, job)
    except InvalidTransitionError as exc:
        raise _transition_or_409(exc) from exc
    await _publish_control(redis, ControlAction.PAUSE, job)
    return CrawlJobResponse.model_validate(job)


@router.post("/{job_id}/resume", response_model=CrawlJobResponse)
async def resume_crawl_job(
    db: DbDep, redis: RedisDep, _admin: AdminUser, job_id: uuid.UUID
) -> CrawlJobResponse:
    job = await _get_job_or_404(db, job_id)
    try:
        job = await service.resume(db, job)
    except InvalidTransitionError as exc:
        raise _transition_or_409(exc) from exc
    await _publish_control(redis, ControlAction.RESUME, job)
    return CrawlJobResponse.model_validate(job)


@router.post("/{job_id}/cancel", response_model=CrawlJobResponse)
async def cancel_crawl_job(
    db: DbDep, redis: RedisDep, _admin: AdminUser, job_id: uuid.UUID
) -> CrawlJobResponse:
    job = await _get_job_or_404(db, job_id)
    try:
        job = await service.cancel(db, job)
    except InvalidTransitionError as exc:
        raise _transition_or_409(exc) from exc
    await _publish_control(redis, ControlAction.CANCEL, job)
    return CrawlJobResponse.model_validate(job)
