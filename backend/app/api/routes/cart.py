from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.dependencies import CurrentUser, SessionDep
from app.schemas.cart import CartItemCreate, CartRead
from app.schemas.common import error_responses
from app.services import cart as cart_service

router = APIRouter(prefix="/cart", tags=["cart"])


@router.get("", response_model=CartRead, responses=error_responses(401))
async def get_cart(user: CurrentUser, session: SessionDep) -> CartRead:
    return await cart_service.build_cart(session, user.id)


@router.post(
    "/items",
    response_model=CartRead,
    responses=error_responses(401, 404, 409, 422),
    description="Idempotent: adding a book that is already in the cart changes nothing. "
    "Returns 409 BOOK_UNAVAILABLE when the copy is reserved or not available.",
)
async def add_cart_item(body: CartItemCreate, user: CurrentUser, session: SessionDep) -> CartRead:
    return await cart_service.add_item(session, user, body.book_id)


@router.delete("/items/{book_id}", response_model=CartRead, responses=error_responses(401, 422))
async def remove_cart_item(book_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> CartRead:
    return await cart_service.remove_item(session, user, book_id)


@router.delete("", response_model=CartRead, responses=error_responses(401))
async def clear_cart(user: CurrentUser, session: SessionDep) -> CartRead:
    return await cart_service.clear(session, user)
