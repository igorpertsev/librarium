from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status

from app.api.dependencies import CurrentUser, SessionDep
from app.schemas.common import error_responses
from app.schemas.waitlist import WaitlistEntryRead
from app.services import waitlist as waitlist_service

router = APIRouter(prefix="/waitlist", tags=["waitlist"])


@router.get("", response_model=list[WaitlistEntryRead], responses=error_responses(401))
async def my_waitlist(user: CurrentUser, session: SessionDep) -> list[WaitlistEntryRead]:
    entries = await waitlist_service.list_entries(session, user)
    return [WaitlistEntryRead.model_validate(entry) for entry in entries]


@router.post(
    "/{book_id}",
    response_model=WaitlistEntryRead,
    responses={
        201: {"model": WaitlistEntryRead, "description": "Added to the waiting list"},
        **error_responses(401, 404, 409, 422),
    },
    description="Email me when this book is available again. Idempotent: 201 when added, "
    "200 when already waiting. 409 BOOK_AVAILABLE if the book can be ordered right now.",
)
async def join_waitlist(
    book_id: uuid.UUID, user: CurrentUser, session: SessionDep, response: Response
) -> WaitlistEntryRead:
    entry, created = await waitlist_service.join(session, user, book_id)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return WaitlistEntryRead.model_validate(entry)


@router.delete(
    "/{book_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(401, 422),
)
async def leave_waitlist(book_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> Response:
    await waitlist_service.leave(session, user, book_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
