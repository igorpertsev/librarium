from __future__ import annotations

from typing import Literal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LibrarySettings
from app.models.library_settings import DEFAULT_LIBRARY_SETTINGS, SETTINGS_ROW_ID
from app.schemas.library_settings import LibrarySettingsUpdate


async def ensure_library_settings(session: AsyncSession) -> None:
    """Insert the default settings row if it is missing (idempotent)."""
    await session.execute(
        pg_insert(LibrarySettings).values(**DEFAULT_LIBRARY_SETTINGS).on_conflict_do_nothing()
    )


async def get_library_settings(
    session: AsyncSession, *, lock: Literal["share", "update"] | None = None
) -> LibrarySettings:
    stmt = select(LibrarySettings).where(LibrarySettings.id == SETTINGS_ROW_ID)
    if lock == "share":
        stmt = stmt.with_for_update(read=True)
    elif lock == "update":
        stmt = stmt.with_for_update()
    row = await session.scalar(stmt)
    if row is None:
        # The initial migration inserts this row; recreate it defensively.
        await ensure_library_settings(session)
        row = (await session.scalars(stmt)).one()
    return row


async def update_library_settings(
    session: AsyncSession, patch: LibrarySettingsUpdate
) -> LibrarySettings:
    row = await get_library_settings(session, lock="update")
    for field, value in patch.changes().items():
        setattr(row, field, value)
    await session.commit()
    return row
