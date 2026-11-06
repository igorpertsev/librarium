"""Tags and series that readers browse by (public)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.dependencies import SessionDep
from app.schemas.catalog import SeriesRead, TagRead
from app.schemas.common import error_responses
from app.services import catalog

router = APIRouter(tags=["catalogue"])


@router.get("/tags", response_model=list[TagRead])
async def list_tags(session: SessionDep) -> list[TagRead]:
    """Every tag with the number of titles that have it (filter: GET /books?tags=a,b)."""
    return await catalog.list_tags(session)


@router.get("/series", response_model=list[SeriesRead])
async def list_series(
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=200, description="Part of the name")] = None,
) -> list[SeriesRead]:
    """Series by name (books of one: GET /books?series=<id>&sort=series)."""
    return await catalog.list_series(session, q)


@router.get("/series/{series_id}", response_model=SeriesRead, responses=error_responses(404, 422))
async def get_series(series_id: uuid.UUID, session: SessionDep) -> SeriesRead:
    return await catalog.get_series(session, series_id)
