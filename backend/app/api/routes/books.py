from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.dependencies import PaginationDep, SessionDep
from app.models.enums import BookCategory
from app.repositories.books import BookFilters
from app.schemas.book import BookPage, BookRead, BookSort, SeriesNeighbours
from app.schemas.common import error_responses
from app.services import books as books_service
from app.services import series_reading

router = APIRouter(prefix="/books", tags=["books"])

SearchQuery = Annotated[
    str | None,
    Query(max_length=200, description="Matches title, author, ISBN, description, tags, series"),
]
TagsQuery = Annotated[
    str | None,
    Query(
        max_length=300,
        pattern=r"^[a-z0-9-]+(,[a-z0-9-]+){0,9}$",
        description="Comma-separated tag slugs; a book must have all of them",
    ),
]


LanguageQuery = Annotated[
    str | None,
    Query(pattern=r"^[a-z]{2,3}$", description="ISO 639 code of the book's language, e.g. en"),
]


def tag_slugs(tags: str | None) -> tuple[str, ...]:
    return tuple(dict.fromkeys(tags.split(","))) if tags else ()


@router.get("", response_model=BookPage, responses=error_responses(422))
async def list_books(
    session: SessionDep,
    pagination: PaginationDep,
    q: SearchQuery = None,
    category: BookCategory | None = None,
    age_range: Annotated[str | None, Query(max_length=20)] = None,
    available: Annotated[
        bool | None, Query(description="true: can be borrowed now; false: cannot")
    ] = None,
    tags: TagsQuery = None,
    series: Annotated[uuid.UUID | None, Query(description="Books of this series")] = None,
    language: LanguageQuery = None,
    sort: BookSort = BookSort.TITLE,
) -> BookPage:
    items, total = await books_service.list_books(
        session,
        BookFilters(
            q=q.strip() if q else None,
            category=category,
            age_range=age_range,
            available=available,
            tags=tag_slugs(tags),
            series_id=series,
            language=language,
        ),
        sort=sort,
        page=pagination.page,
        page_size=pagination.page_size,
        group_copies=True,  # one entry per title; see BookRead.copies
    )
    return BookPage(items=items, total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/age-ranges", response_model=list[str])
async def list_age_ranges(session: SessionDep) -> list[str]:
    return list(await books_service.age_ranges(session))


@router.get(
    "/languages",
    response_model=list[str],
    description="Languages (ISO 639 codes) of the books in the catalogue, for the filter.",
)
async def list_languages(session: SessionDep) -> list[str]:
    return list(await books_service.languages(session))


@router.get(
    "/{book_id}/series-neighbours",
    response_model=SeriesNeighbours,
    responses=error_responses(404, 422),
    description="The numbered volumes just before and after this book in its series.",
)
async def get_series_neighbours(book_id: uuid.UUID, session: SessionDep) -> SeriesNeighbours:
    found = await series_reading.neighbours(session, book_id)
    return SeriesNeighbours(previous=found.previous, next=found.next)


@router.get("/{book_id}", response_model=BookRead, responses=error_responses(404, 422))
async def get_book(book_id: uuid.UUID, session: SessionDep) -> BookRead:
    return await books_service.get_book(session, book_id)
