from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Response, status
from fastapi.responses import JSONResponse

from app.api.dependencies import CurrentUser, SessionDep, SettingsDep
from app.api.routes.auth import clear_refresh_cookie
from app.schemas.book import BookRead
from app.schemas.common import error_responses
from app.schemas.hold import HeldBookRead
from app.schemas.user import DeleteAccountRequest, UserRead, UserUpdate
from app.services import account, holds, recommendations, series_reading
from app.services import users as users_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead, responses=error_responses(401))
async def read_me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.patch("/me", response_model=UserRead, responses=error_responses(401, 409, 422))
async def update_me(body: UserUpdate, user: CurrentUser, session: SessionDep) -> UserRead:
    updated = await users_service.update_profile(session, user, body)
    return UserRead.model_validate(updated)


@router.get(
    "/me/next-in-series",
    response_model=list[BookRead],
    responses=error_responses(401),
    description="For each series the reader has borrowed from, the first volume after the "
    "furthest one they borrowed that they have not borrowed yet.",
)
async def my_next_in_series(user: CurrentUser, session: SessionDep) -> list[BookRead]:
    return await series_reading.next_for_reader(session, user)


@router.get(
    "/me/recommendations",
    response_model=list[BookRead],
    responses=error_responses(401),
    description="Up to 8 titles the reader has not borrowed or saved, ranked by the tags of the "
    "titles they borrowed and saved.",
)
async def my_recommendations(user: CurrentUser, session: SessionDep) -> list[BookRead]:
    return await recommendations.for_reader(session, user.id)


@router.get(
    "/me/holds",
    response_model=list[HeldBookRead],
    responses=error_responses(401),
    description="Books held for the reader after they waited for them, until held_until. The "
    "reader can add the held copy to the cart; nobody else can.",
)
async def my_holds(user: CurrentUser, session: SessionDep) -> list[HeldBookRead]:
    found = await holds.list_for(session, user, datetime.now(UTC))
    return [HeldBookRead(book=item.book, held_until=item.held_until) for item in found]


@router.delete(
    "/me/holds/{book_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(401, 422),
    description="Give up a held book: it goes to the next reader in line.",
)
async def release_hold(book_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> Response:
    await holds.release(session, user, book_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/me/export",
    responses=error_responses(401),
    description="Everything stored about the signed-in reader, as a JSON file.",
)
async def export_my_data(user: CurrentUser, session: SessionDep) -> JSONResponse:
    data = await account.export_data(session, user)
    return JSONResponse(
        data,
        headers={"Content-Disposition": 'attachment; filename="little-dragon-my-data.json"'},
    )


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(400, 401, 409, 422),
    description="Deletes the account after checking the password: personal data is removed, "
    "orders stay for the library's records without the reader's name or contacts. 409 "
    "ACTIVE_ORDERS while books are requested or on loan; 409 ADMIN_ACCOUNT for administrators.",
)
async def delete_me(
    body: DeleteAccountRequest, user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> Response:
    await account.delete_account(session, user, body.password)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_refresh_cookie(response, settings)
    return response
