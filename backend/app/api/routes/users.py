from __future__ import annotations

from fastapi import APIRouter

from app.api.dependencies import CurrentUser, SessionDep
from app.schemas.common import error_responses
from app.schemas.user import UserRead, UserUpdate
from app.services import users as users_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead, responses=error_responses(401))
async def read_me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.patch("/me", response_model=UserRead, responses=error_responses(401, 409, 422))
async def update_me(body: UserUpdate, user: CurrentUser, session: SessionDep) -> UserRead:
    updated = await users_service.update_profile(session, user, body)
    return UserRead.model_validate(updated)
