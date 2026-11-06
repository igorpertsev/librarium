from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.dependencies import CurrentUser, PaginationDep, SessionDep
from app.models.enums import OrderStatus
from app.repositories import orders as orders_repo
from app.schemas.common import error_responses
from app.schemas.order import OrderPage, OrderRead
from app.services import orders as orders_service

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=OrderRead,
    responses=error_responses(400, 401, 409),
    description="Places an order for every complete batch in the cart. Books of an incomplete "
    "trailing batch stay in the cart. Prices are computed by the server. Responds 409 "
    "BOOK_UNAVAILABLE (details.book_ids) when any copy is no longer available; in that case "
    "nothing is created.",
)
async def place_order(user: CurrentUser, session: SessionDep) -> OrderRead:
    order = await orders_service.place_order(session, user)
    return OrderRead.model_validate(order)


@router.get("", response_model=OrderPage, responses=error_responses(401, 422))
async def list_my_orders(
    user: CurrentUser,
    session: SessionDep,
    pagination: PaginationDep,
    status: OrderStatus | None = None,
) -> OrderPage:
    orders, total = await orders_repo.list_orders(
        session,
        user_id=user.id,
        status=status,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return OrderPage(
        items=[OrderRead.model_validate(o) for o in orders],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/{order_id}", response_model=OrderRead, responses=error_responses(401, 404, 422))
async def get_my_order(order_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> OrderRead:
    # Other users' orders are reported as 404 so their existence is not revealed.
    order = await orders_service.get_order(session, order_id, user_id=user.id)
    return OrderRead.model_validate(order)


@router.post(
    "/{order_id}/cancel", response_model=OrderRead, responses=error_responses(401, 404, 409, 422)
)
async def cancel_my_order(order_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> OrderRead:
    order = await orders_service.cancel_own_order(session, user, order_id)
    return OrderRead.model_validate(order)
