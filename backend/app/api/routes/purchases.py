from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.dependencies import CurrentUser, SessionDep
from app.models.enums import PurchaseStatus
from app.schemas.common import error_responses
from app.schemas.purchase import (
    PurchaseRequestCreate,
    PurchaseRequestCreated,
    PurchaseRequestRead,
)
from app.services import purchases

router = APIRouter(prefix="/purchase-requests", tags=["purchase requests"])


@router.get("", response_model=list[PurchaseRequestRead], responses=error_responses(401, 422))
async def list_purchase_requests(
    user: CurrentUser,
    session: SessionDep,
    status_: Annotated[list[PurchaseStatus] | None, Query(alias="status")] = None,
) -> list[PurchaseRequestRead]:
    """Suggestions with the most votes first (default: open and ordered ones)."""
    statuses = tuple(status_) if status_ else purchases.ACTIVE
    found = await purchases.list_requests(session, user, statuses)
    return [PurchaseRequestRead.model_validate(r, from_attributes=True) for r in found]


@router.post(
    "",
    response_model=PurchaseRequestCreated,
    responses=error_responses(401, 409, 422),
    description="Suggest a book for the library to buy. The same book suggested earlier gets a "
    "vote instead (created=false). 409 ALREADY_IN_CATALOGUE (details.book_id) or "
    "TOO_MANY_SUGGESTIONS (10 open ones per reader).",
)
async def suggest_purchase(
    body: PurchaseRequestCreate, user: CurrentUser, session: SessionDep, response: Response
) -> PurchaseRequestCreated:
    view, created = await purchases.suggest(
        session, user, title=body.title, author=body.author, isbn=body.isbn, note=body.note
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return PurchaseRequestCreated(
        request=PurchaseRequestRead.model_validate(view, from_attributes=True), created=created
    )


@router.put(
    "/{request_id}/vote",
    response_model=PurchaseRequestRead,
    responses=error_responses(401, 404, 422),
)
async def vote_for_purchase(
    request_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> PurchaseRequestRead:
    view = await purchases.vote(session, user, request_id)
    return PurchaseRequestRead.model_validate(view, from_attributes=True)


@router.delete(
    "/{request_id}/vote",
    response_model=PurchaseRequestRead,
    responses=error_responses(401, 404, 422),
)
async def withdraw_purchase_vote(
    request_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> PurchaseRequestRead:
    view = await purchases.unvote(session, user, request_id)
    return PurchaseRequestRead.model_validate(view, from_attributes=True)
