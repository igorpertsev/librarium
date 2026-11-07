from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.dependencies import SessionDep, SettingsDep
from app.schemas.collection import BookPick
from app.schemas.common import error_responses
from app.schemas.library_settings import LibraryRules
from app.schemas.pickup import PickupPointRead, PickupSlot
from app.services import collections, pickup
from app.services import library_settings as settings_service

router = APIRouter(prefix="/library", tags=["library"])


@router.get("/rules", response_model=LibraryRules)
async def library_rules(session: SessionDep, settings: SettingsDep) -> LibraryRules:
    """Batch size and price, loan period and how often a loan can be extended."""
    row = await settings_service.get_library_settings(session)
    rules = LibraryRules.model_validate(row)
    bot = settings.telegram_bot_username if settings.telegram_bot_token else None
    push = settings.web_push_public_key if settings.web_push_enabled else None
    return rules.model_copy(
        update={
            "telegram_bot": bot,
            "web_push_key": push,
            "has_pick": row.pick_group_id is not None,
        }
    )


@router.get("/pickup-points", response_model=list[PickupPointRead])
async def pickup_points(session: SessionDep) -> list[PickupPointRead]:
    """Where readers can collect their orders (active points only). An empty list means
    orders need no pickup point."""
    return [PickupPointRead.model_validate(p) for p in await pickup.list_active(session)]


@router.get(
    "/pickup-points/{point_id}/slots",
    response_model=list[PickupSlot],
    responses=error_responses(404, 422),
)
async def pickup_slots(point_id: uuid.UUID, session: SessionDep) -> list[PickupSlot]:
    """Pickup times for the next two weeks, starting at least an hour from now."""
    return [PickupSlot.model_validate(slot) for slot in await pickup.slots(session, point_id)]


@router.get("/pick", response_model=BookPick | None)
async def book_of_the_month(session: SessionDep) -> BookPick | None:
    """The librarians' book of the month with its note (null: none chosen)."""
    chosen = await collections.pick(session)
    return BookPick.model_validate(chosen, from_attributes=True) if chosen else None
