from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.dependencies import PaginationDep, SessionDep
from app.models.enums import BookCategory
from app.repositories.books import BookFilters
from app.schemas.book import BookPage, BookRead, BookSort
from app.schemas.common import error_responses
from app.services import books as books_service

router = APIRouter(prefix="/books", tags=["books"])

SearchQuery = Annotated[
    str | None, Query(max_length=200, description="Matches title, author or ISBN")
]


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
    sort: BookSort = BookSort.TITLE,
) -> BookPage:
    items, total = await books_service.list_books(
        session,
        BookFilters(
            q=q.strip() if q else None,
            category=category,
            age_range=age_range,
            available=available,
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


@router.get("/{book_id}", response_model=BookRead, responses=error_responses(404, 422))
async def get_book(book_id: uuid.UUID, session: SessionDep) -> BookRead:
    return await books_service.get_book(session, book_id)
