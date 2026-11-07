"""Reading challenges for readers: the current ones with their progress; joining and leaving."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Response, status

from app.api.dependencies import CurrentUser, SessionDep
from app.api.routes.users import ChildQuery
from app.schemas.challenge import ChallengeProgress, ChallengeRead
from app.schemas.common import error_responses
from app.services import challenges
from app.services.library_settings import get_library_settings

router = APIRouter(prefix="/challenges", tags=["challenges"])


def challenge_read(view: challenges.ChallengeView) -> ChallengeRead:
    return ChallengeRead.model_validate(
        {
            **{c.key: getattr(view.challenge, c.key) for c in view.challenge.__table__.columns},
            "participants": view.participants,
            "completed": view.completed,
            "mine": [ChallengeProgress.model_validate(p, from_attributes=True) for p in view.mine],
        }
    )


async def _today(session: SessionDep) -> datetime:
    zone = ZoneInfo((await get_library_settings(session)).timezone)
    return datetime.now(UTC).astimezone(zone)


@router.get("", response_model=list[ChallengeRead], responses=error_responses(401))
async def list_challenges(user: CurrentUser, session: SessionDep) -> list[ChallengeRead]:
    """Challenges that are on or coming up, with the reader's (and children's) progress."""
    today = (await _today(session)).date()
    return [challenge_read(v) for v in await challenges.current(session, user, today)]


@router.put(
    "/{challenge_id}/entry",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(401, 404, 409, 422),
    description="Take part (``?child=`` for a child profile). 409 CHALLENGE_OVER after its end.",
)
async def join_challenge(
    challenge_id: uuid.UUID, user: CurrentUser, session: SessionDep, child: ChildQuery = None
) -> Response:
    today = (await _today(session)).date()
    await challenges.join(session, user, challenge_id, child, today)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{challenge_id}/entry",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(401, 422),
)
async def leave_challenge(
    challenge_id: uuid.UUID, user: CurrentUser, session: SessionDep, child: ChildQuery = None
) -> Response:
    """Stop taking part (the books read stay in the reading log)."""
    await challenges.leave(session, user, challenge_id, child)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
