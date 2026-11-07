from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status

from app.api.dependencies import CurrentUser, SessionDep
from app.schemas.common import error_responses
from app.schemas.review import MyReviewRead, ReviewRead, ReviewWrite
from app.services import reviews

router = APIRouter(prefix="/books", tags=["reviews"])


@router.get(
    "/{book_id}/my-review",
    response_model=MyReviewRead,
    responses=error_responses(401, 404, 422),
)
async def my_review(book_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> MyReviewRead:
    can_review, review = await reviews.mine(session, user, book_id)
    return MyReviewRead(
        can_review=can_review, review=ReviewRead.model_validate(review) if review else None
    )


@router.put(
    "/{book_id}/my-review",
    response_model=ReviewRead,
    responses=error_responses(401, 403, 404, 422),
    description="Rate (and optionally review) a title the reader borrowed; replaces their "
    "earlier review. A rating alone is published at once, text waits for a librarian. 403 "
    "NOT_BORROWED otherwise.",
)
async def save_my_review(
    book_id: uuid.UUID, body: ReviewWrite, user: CurrentUser, session: SessionDep
) -> ReviewRead:
    review = await reviews.save(session, user, book_id, rating=body.rating, text=body.text)
    return ReviewRead.model_validate(review)


@router.delete(
    "/{book_id}/my-review",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(401, 404, 422),
)
async def delete_my_review(book_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> Response:
    await reviews.delete_mine(session, user, book_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
