"""Password reset by email.

The link carries a signed token (see ``create_password_reset_token``); nothing is stored in
the database. The token expires after ``PASSWORD_RESET_EXPIRE_MINUTES`` and stops working
as soon as the password changes, so each link can be used once.
"""

from __future__ import annotations

from email.message import EmailMessage

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import BadRequestError
from app.core.security import (
    InvalidPasswordResetTokenError,
    create_password_reset_token,
    decode_password_reset_token,
    hash_password,
    password_fingerprint,
)
from app.models import User
from app.repositories.users import get_user_by_email
from app.services.auth import revoke_user_tokens
from app.services.notifications import build_message


def invalid_link_error() -> BadRequestError:
    return BadRequestError(
        "This password reset link is invalid or has expired", code="INVALID_RESET_TOKEN"
    )


def _render(user: User, link: str, minutes: int) -> tuple[str, str]:
    subject = "Reset your password · Сброс пароля"
    body = (
        f"Hello {user.full_name},\n\n"
        "someone (hopefully you) asked to reset the password of your Little Dragon library "
        "account. Open this link to choose a new password:\n\n"
        f"{link}\n\n"
        f"The link works for {minutes} minutes and only once. If you did not ask for this, "
        "ignore this email: your password stays the same.\n\n"
        "— Little Dragon library\n\n"
        "----------------------------------------\n\n"
        f"Здравствуйте, {user.full_name}!\n\n"
        "кто-то (надеемся, вы) запросил сброс пароля вашей учётной записи в библиотеке "
        "Little Dragon. Чтобы задать новый пароль, откройте ссылку:\n\n"
        f"{link}\n\n"
        f"Ссылка действует {minutes} минут и только один раз. Если вы не запрашивали сброс, "
        "просто проигнорируйте это письмо — пароль останется прежним.\n\n"
        "— Библиотека Little Dragon\n"
    )
    return subject, body


async def build_reset_email(
    session: AsyncSession, settings: Settings, email: str
) -> EmailMessage | None:
    """The reset email for an active account, or None (the caller answers the same way)."""
    user = await get_user_by_email(session, email)
    if user is None or not user.is_active:
        return None
    token = create_password_reset_token(
        user_id=user.id, password_hash=user.password_hash, settings=settings
    )
    # In the fragment, so the token never reaches server or proxy logs.
    link = f"{settings.app_base_url}/reset-password#token={token}"
    subject, body = _render(user, link, settings.password_reset_expire_minutes)
    return build_message(settings, user=user, subject=subject, body=body)


async def reset_password(
    session: AsyncSession, settings: Settings, token: str, new_password: str
) -> None:
    try:
        claims = decode_password_reset_token(token, settings)
    except InvalidPasswordResetTokenError as exc:
        raise invalid_link_error() from exc

    user = await session.get(User, claims.user_id, with_for_update=True)
    if (
        user is None
        or not user.is_active
        or password_fingerprint(user.password_hash) != claims.fingerprint
    ):
        raise invalid_link_error()

    user.password_hash = await hash_password(new_password)
    # Whoever may know the old password is signed out everywhere.
    await revoke_user_tokens(session, user.id)
    await session.commit()
