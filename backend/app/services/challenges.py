"""Reading challenges: the library sets a goal ("10 books this summer", optionally of one
category) for a period; readers join for themselves or for a child, and every title they mark as
read ("I've read it", see app.services.reading_log) within the dates counts. Progress is
computed from the reading log, so it never goes out of step with it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import Select, delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models import Book, Challenge, ChallengeEntry, ChildProfile, ReadingLogEntry, User
from app.services import family


def not_found() -> NotFoundError:
    return NotFoundError("Challenge not found", code="CHALLENGE_NOT_FOUND")


@dataclass(frozen=True, slots=True)
class Progress:
    child_id: uuid.UUID | None
    child_name: str | None
    read: int
    completed: bool


@dataclass(frozen=True, slots=True)
class ChallengeView:
    challenge: Challenge
    participants: int
    completed: int
    mine: list[Progress]


@dataclass(frozen=True, slots=True)
class Participant:
    name: str
    parent_name: str | None  # for a child: the account it belongs to
    read: int
    completed: bool
    joined_at: datetime


def _progress_query() -> Select[ChallengeEntry, int]:
    """Each entry with the number of titles its profile read in the challenge's dates."""
    read = func.count(func.distinct(ReadingLogEntry.book_id))
    return (
        select(ChallengeEntry, read.label("read"))
        .join(Challenge, Challenge.id == ChallengeEntry.challenge_id)
        .outerjoin(
            ReadingLogEntry,
            (ReadingLogEntry.user_id == ChallengeEntry.user_id)
            & ReadingLogEntry.child_id.is_not_distinct_from(ChallengeEntry.child_id)
            & ReadingLogEntry.finished_on.between(Challenge.starts_on, Challenge.ends_on)
            & (
                Challenge.category.is_(None)
                | select(Book.id)
                .where(Book.id == ReadingLogEntry.book_id, Book.category == Challenge.category)
                .exists()
            ),
        )
        .group_by(ChallengeEntry.id)
    )


async def _views(
    session: AsyncSession, challenges: list[Challenge], user: User | None
) -> list[ChallengeView]:
    if not challenges:
        return []
    ids = [c.id for c in challenges]
    rows = (
        await session.execute(_progress_query().where(ChallengeEntry.challenge_id.in_(ids)))
    ).all()
    goals = {c.id: c.goal for c in challenges}
    children = (
        {
            child.id: child.name
            for child in await session.scalars(
                select(ChildProfile).where(ChildProfile.parent_id == user.id)
            )
        }
        if user is not None
        else {}
    )
    counts: dict[uuid.UUID, list[int]] = {i: [0, 0] for i in ids}
    mine: dict[uuid.UUID, list[Progress]] = {i: [] for i in ids}
    for entry, read in rows:
        done = read >= goals[entry.challenge_id]
        counts[entry.challenge_id][0] += 1
        counts[entry.challenge_id][1] += int(done)
        if user is not None and entry.user_id == user.id:
            mine[entry.challenge_id].append(
                Progress(
                    entry.child_id,
                    children.get(entry.child_id) if entry.child_id else None,
                    min(read, 999),
                    done,
                )
            )
    return [
        ChallengeView(
            challenge=c,
            participants=counts[c.id][0],
            completed=counts[c.id][1],
            mine=sorted(mine[c.id], key=lambda p: (p.child_id is not None, p.child_name or "")),
        )
        for c in challenges
    ]


async def current(session: AsyncSession, user: User, today: date) -> list[ChallengeView]:
    """Challenges that are on or coming up, with the reader's own progress."""
    found = (
        await session.scalars(
            select(Challenge).where(Challenge.ends_on >= today).order_by(Challenge.starts_on)
        )
    ).all()
    return await _views(session, list(found), user)


async def everything(session: AsyncSession) -> list[ChallengeView]:
    found = (await session.scalars(select(Challenge).order_by(Challenge.starts_on.desc()))).all()
    return await _views(session, list(found), None)


async def _challenge(session: AsyncSession, challenge_id: uuid.UUID) -> Challenge:
    challenge = await session.get(Challenge, challenge_id)
    if challenge is None:
        raise not_found()
    return challenge


async def join(
    session: AsyncSession,
    user: User,
    challenge_id: uuid.UUID,
    child_id: uuid.UUID | None,
    today: date,
) -> None:
    challenge = await _challenge(session, challenge_id)
    if challenge.ends_on < today:
        raise ConflictError("This challenge is over", code="CHALLENGE_OVER")
    if child_id is not None:
        await family.child_of(session, user, child_id)  # 404 for someone else's child
    await session.execute(
        pg_insert(ChallengeEntry)
        .values(id=uuid.uuid4(), challenge_id=challenge.id, user_id=user.id, child_id=child_id)
        .on_conflict_do_nothing(constraint="uq_challenge_entries_profile")
    )
    await session.commit()


async def leave(
    session: AsyncSession, user: User, challenge_id: uuid.UUID, child_id: uuid.UUID | None
) -> None:
    await session.execute(
        delete(ChallengeEntry).where(
            ChallengeEntry.challenge_id == challenge_id,
            ChallengeEntry.user_id == user.id,
            ChallengeEntry.child_id.is_not_distinct_from(child_id),
        )
    )
    await session.commit()


async def create(session: AsyncSession, values: dict[str, Any]) -> ChallengeView:
    challenge = Challenge(id=uuid.uuid4(), **values)
    session.add(challenge)
    await session.commit()
    return (await _views(session, [challenge], None))[0]


async def update(
    session: AsyncSession, challenge_id: uuid.UUID, changes: dict[str, Any]
) -> ChallengeView:
    challenge = await _challenge(session, challenge_id)
    for name, value in changes.items():
        setattr(challenge, name, value)
    if challenge.ends_on < challenge.starts_on:
        raise ConflictError("The challenge ends before it starts", code="INVALID_DATES")
    await session.commit()
    return (await _views(session, [challenge], None))[0]


async def remove(session: AsyncSession, challenge_id: uuid.UUID) -> None:
    challenge = await _challenge(session, challenge_id)
    await session.delete(challenge)
    await session.commit()


async def participants(session: AsyncSession, challenge_id: uuid.UUID) -> list[Participant]:
    challenge = await _challenge(session, challenge_id)
    rows = (
        await session.execute(
            _progress_query()
            .add_columns(User.full_name, ChildProfile.name)
            .join(User, User.id == ChallengeEntry.user_id)
            .outerjoin(ChildProfile, ChildProfile.id == ChallengeEntry.child_id)
            .where(ChallengeEntry.challenge_id == challenge.id)
            .group_by(User.full_name, ChildProfile.name)
        )
    ).all()
    found = [
        Participant(
            name=child_name or reader,
            parent_name=reader if child_name else None,
            read=read,
            completed=read >= challenge.goal,
            joined_at=entry.joined_at,
        )
        for entry, read, reader, child_name in rows
    ]
    return sorted(found, key=lambda p: (-p.read, p.joined_at))
