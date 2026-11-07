"""Collections of titles put together by the librarians (public)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.api.dependencies import SessionDep
from app.models import Collection
from app.schemas.book import BookRead
from app.schemas.collection import CollectionRead, CollectionSummary
from app.schemas.common import error_responses
from app.services import collections

router = APIRouter(prefix="/collections", tags=["collections"])


def summary_of(collection: Collection, book_count: int) -> CollectionSummary:
    return CollectionSummary.model_validate(
        {
            **{c.key: getattr(collection, c.key) for c in collection.__table__.columns},
            "book_count": book_count,
        }
    )


def read_of(collection: Collection, books: list[BookRead]) -> CollectionRead:
    return CollectionRead(**summary_of(collection, len(books)).model_dump(), books=books)


@router.get("", response_model=list[CollectionSummary])
async def list_collections(
    session: SessionDep,
    featured: Annotated[bool, Query(description="Only those shown on the catalogue")] = False,
) -> list[CollectionSummary]:
    found = await collections.summaries(session, featured_only=featured)
    return [summary_of(s.collection, s.book_count) for s in found]


@router.get("/{slug}", response_model=CollectionRead, responses=error_responses(404, 422))
async def get_collection(
    session: SessionDep, slug: Annotated[str, Path(max_length=80)]
) -> CollectionRead:
    collection, books = await collections.detail(session, slug)
    return read_of(collection, books)
