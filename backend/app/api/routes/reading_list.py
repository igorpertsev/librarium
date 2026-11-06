from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status

from app.api.dependencies import CurrentUser, SessionDep
from app.schemas.common import error_responses
from app.schemas.reading_list import ReadingListItemRead
from app.services import reading_list as reading_list_service

router = APIRouter(prefix="/reading-list", tags=["reading list"])


@router.get(
    "",
    response_model=list[ReadingListItemRead],
    responses=error_responses(401),
    description='"Want to read": one entry per title, newest first, each with the copy that '
    "can be borrowed now if there is one.",
)
async def my_reading_list(user: CurrentUser, session: SessionDep) -> list[ReadingListItemRead]:
    items = await reading_list_service.list_items(session, user)
    return [ReadingListItemRead(book=item.book, created_at=item.created_at) for item in items]


@router.post(
    "/{book_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(401, 404, 422),
    description="Add the title of this copy. Idempotent.",
)
async def add_to_reading_list(
    book_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> Response:
    await reading_list_service.add(session, user, book_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{book_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(401, 422),
    description="Remove the title of this copy. Idempotent.",
)
async def remove_from_reading_list(
    book_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> Response:
    await reading_list_service.remove(session, user, book_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
