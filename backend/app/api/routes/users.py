from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.dependencies import CurrentUser, SessionDep, SettingsDep
from app.api.routes.auth import clear_refresh_cookie
from app.schemas.auth import MfaEnableRequest, MfaRecoveryCodes, MfaSetup, MfaSetupRequest
from app.schemas.book import BookRead
from app.schemas.common import error_responses
from app.schemas.family import ChildCreate, ChildRead, ChildUpdate
from app.schemas.hold import HeldBookRead
from app.schemas.inbox import Inbox, MarkRead
from app.schemas.passkey import PasskeyOptions, PasskeyOptionsRequest, PasskeyRead, PasskeyRegister
from app.schemas.push import PushSubscriptionCreate
from app.schemas.reading_log import MarkFinished, ReadingLogRead
from app.schemas.reservation import ReservationCreate, ReservationRead
from app.schemas.user import (
    CalendarLink,
    DeleteAccountRequest,
    TelegramLink,
    UserRead,
    UserUpdate,
)
from app.services import (
    account,
    calendar,
    family,
    holds,
    inbox,
    mfa,
    passkeys,
    reading_log,
    recommendations,
    reservations,
    series_reading,
    telegram,
    web_push,
)
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


@router.post(
    "/me/mfa/setup",
    response_model=MfaSetup,
    responses=error_responses(400, 401, 409, 422),
    description="Start two-step sign-in: confirm the password, then scan the otpauth link (as a "
    "QR code) with an authenticator app and confirm with /me/mfa/enable.",
)
async def start_mfa_setup(
    body: MfaSetupRequest, user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> MfaSetup:
    setup = await mfa.start_setup(session, settings, user, body.password)
    return MfaSetup(secret=setup.secret, otpauth_uri=setup.otpauth_uri)


@router.post(
    "/me/mfa/enable",
    response_model=MfaRecoveryCodes,
    responses=error_responses(400, 401, 409, 422),
)
async def enable_mfa(
    body: MfaEnableRequest, user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> MfaRecoveryCodes:
    """Turn it on with a first code from the app; returns ten recovery codes, shown once."""
    return MfaRecoveryCodes(recovery_codes=await mfa.enable(session, settings, user, body.code))


@router.post(
    "/me/mfa/disable",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(400, 401, 409, 422),
)
async def disable_mfa(body: MfaSetupRequest, user: CurrentUser, session: SessionDep) -> Response:
    """Turn it off (password needed; 409 MFA_REQUIRED_BY_LIBRARY for staff when required)."""
    await mfa.disable(session, user, body.password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/me/telegram/link",
    response_model=TelegramLink,
    responses=error_responses(401, 409),
    description="A one-time link that opens the library's Telegram bot; pressing Start there "
    "connects the chat (15 minutes). 409 TELEGRAM_NOT_CONFIGURED without a bot.",
)
async def link_telegram(
    user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> TelegramLink:
    url, expires = await telegram.start_link(session, settings, user)
    return TelegramLink(url=url, expires_at=expires)


@router.delete(
    "/me/telegram",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(401),
)
async def unlink_telegram(user: CurrentUser, session: SessionDep) -> Response:
    """Stop sending notifications to Telegram."""
    await telegram.unlink(session, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/me/push-subscriptions",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(401, 409, 422),
    description="Notifications on this device (Web Push): the browser's subscription. "
    "409 PUSH_NOT_CONFIGURED when the library has no push keys.",
)
async def add_push_subscription(
    body: PushSubscriptionCreate,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
) -> Response:
    await web_push.subscribe(
        session,
        settings,
        user,
        endpoint=body.endpoint,
        p256dh=body.keys.p256dh,
        auth=body.keys.auth,
        user_agent=request.headers.get("user-agent"),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/me/push-subscriptions",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(401, 422),
)
async def remove_push_subscription(
    user: CurrentUser,
    session: SessionDep,
    endpoint: Annotated[str, Query(max_length=2048, description="The subscription's endpoint")],
) -> Response:
    """No more notifications on that device."""
    await web_push.unsubscribe(session, user, endpoint)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/me/calendar",
    response_model=CalendarLink,
    responses=error_responses(401),
    description="A new secret link to the reader's calendar feed (due dates, pickups, holds, "
    "reservations); an earlier link stops working.",
)
async def new_calendar_link(
    user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> CalendarLink:
    return CalendarLink(url=await calendar.new_link(session, settings, user))


@router.delete(
    "/me/calendar",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(401),
)
async def remove_calendar_link(user: CurrentUser, session: SessionDep) -> Response:
    """Turn the calendar feed off (its link stops working)."""
    await calendar.remove_link(session, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/me/passkeys/options",
    response_model=PasskeyOptions,
    responses=error_responses(400, 401, 422),
    description="Start adding a passkey (password needed): options for "
    "navigator.credentials.create() and a state to send back.",
)
async def passkey_registration_options(
    body: PasskeyOptionsRequest, user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> PasskeyOptions:
    options, state = await passkeys.registration_options(session, settings, user, body.password)
    return PasskeyOptions(options=options, state=state)


@router.post(
    "/me/passkeys",
    response_model=PasskeyRead,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(400, 401, 409, 422),
)
async def add_passkey(
    body: PasskeyRegister, user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> PasskeyRead:
    """Finish adding a passkey with the browser's answer."""
    made = await passkeys.register(
        session, settings, user, state=body.state, credential=body.credential, name=body.name
    )
    return PasskeyRead.model_validate(made)


@router.get("/me/passkeys", response_model=list[PasskeyRead], responses=error_responses(401))
async def list_passkeys(user: CurrentUser, session: SessionDep) -> list[PasskeyRead]:
    return [PasskeyRead.model_validate(p) for p in await passkeys.list_passkeys(session, user)]


@router.delete(
    "/me/passkeys/{passkey_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(401, 404),
)
async def remove_passkey(passkey_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> Response:
    await passkeys.remove(session, user, passkey_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# A child profile of the account ("?child=<id>"); without it, the reader themselves.
ChildQuery = Annotated[uuid.UUID | None, Query(description="A child profile of the account")]


@router.get("/me/children", response_model=list[ChildRead], responses=error_responses(401))
async def my_children(user: CurrentUser, session: SessionDep) -> list[ChildRead]:
    return [ChildRead.model_validate(c) for c in await family.list_children(session, user)]


@router.post(
    "/me/children",
    status_code=status.HTTP_201_CREATED,
    response_model=ChildRead,
    responses=error_responses(401, 409, 422),
    description="Add a child profile (up to 6): they get their own reading log and badges, and "
    "orders can say they are for them.",
)
async def add_child(body: ChildCreate, user: CurrentUser, session: SessionDep) -> ChildRead:
    child = await family.add_child(session, user, name=body.name, birth_year=body.birth_year)
    return ChildRead.model_validate(child)


@router.patch(
    "/me/children/{child_id}",
    response_model=ChildRead,
    responses=error_responses(401, 404, 422),
)
async def update_child(
    child_id: uuid.UUID, body: ChildUpdate, user: CurrentUser, session: SessionDep
) -> ChildRead:
    return ChildRead.model_validate(
        await family.update_child(session, user, child_id, body.changes())
    )


@router.delete(
    "/me/children/{child_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(401, 404, 422),
)
async def remove_child(child_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> Response:
    """Their reading log goes too; orders keep the name they were placed for."""
    await family.remove_child(session, user, child_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/me/reading-log",
    response_model=ReadingLogRead,
    responses=error_responses(401),
    description="Titles the reader has finished (newest first), counts, badges and borrowed "
    "titles not logged yet.",
)
async def my_reading_log(
    user: CurrentUser, session: SessionDep, child: ChildQuery = None
) -> ReadingLogRead:
    log = await reading_log.reading_log(session, user, child)
    return ReadingLogRead.model_validate(log, from_attributes=True)


@router.put(
    "/me/reading-log/{book_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(400, 401, 404, 422),
    description="Log the title as finished (finished_on defaults to today; not in the future).",
)
async def mark_finished(
    book_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    body: MarkFinished | None = None,
    child: ChildQuery = None,
) -> Response:
    await reading_log.mark_read(session, user, book_id, body.finished_on if body else None, child)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/me/reading-log/{book_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(401, 422),
)
async def unmark_finished(
    book_id: uuid.UUID, user: CurrentUser, session: SessionDep, child: ChildQuery = None
) -> Response:
    await reading_log.unmark(session, user, book_id, child)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/me/notifications",
    response_model=Inbox,
    responses=error_responses(401),
    description="The reader's latest news (up to 30 from the last 60 days), newest first, and "
    "how many are unread. The same events as the emails, even when an email could not be sent.",
)
async def my_notifications(user: CurrentUser, session: SessionDep) -> Inbox:
    return await inbox.inbox(session, user)


@router.post(
    "/me/notifications/read",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(401, 422),
)
async def mark_notifications_read(
    user: CurrentUser, session: SessionDep, body: MarkRead | None = None
) -> Response:
    await inbox.mark_read(session, user, body.ids if body else None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/me/reservations",
    response_model=list[ReservationRead],
    responses=error_responses(401),
    description="Books the reader reserved for a date, soonest first.",
)
async def my_reservations(user: CurrentUser, session: SessionDep) -> list[ReservationRead]:
    found = await reservations.list_for(session, user)
    return [ReservationRead.model_validate(item, from_attributes=True) for item in found]


@router.post(
    "/me/reservations",
    status_code=status.HTTP_201_CREATED,
    response_model=ReservationRead,
    responses=error_responses(400, 401, 404, 409, 422),
    description="Reserve a title for a day from tomorrow to 90 days ahead. A copy that can be "
    "free then is set aside; on the day it is held for the reader, who gets an email. 409 "
    "NO_COPY_FOR_DATE, ALREADY_RESERVED or TOO_MANY_RESERVATIONS (5 at a time).",
)
async def reserve_ahead(
    body: ReservationCreate, user: CurrentUser, session: SessionDep
) -> ReservationRead:
    created = await reservations.create(session, user, body.book_id, body.starts_on)
    return ReservationRead.model_validate(created, from_attributes=True)


@router.delete(
    "/me/reservations/{reservation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(401, 404, 422),
)
async def cancel_reservation(
    reservation_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> Response:
    await reservations.cancel(session, user, reservation_id)
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
