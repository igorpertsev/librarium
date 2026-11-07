"""The keys that encrypt two-step sign-in secrets: MFA_ENCRYPTION_KEYS and rotation."""

from __future__ import annotations

import secrets
import time
import uuid

import pytest
from fastapi import FastAPI
from pydantic import SecretStr, ValidationError

from app.core import totp
from app.core.config import Settings
from app.models import User
from app.services import mfa
from tests.conftest import API, ApiUser, MakeClient, SwapSettings
from tests.test_mfa import _password_step, _turn_on


def test_the_first_key_encrypts_and_every_key_decrypts() -> None:
    old, new = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    sealed = totp.SecretBox([old]).seal("JBSWY3DPEHPK3PXP")
    both = totp.SecretBox([new, old])
    assert both.open(sealed) == "JBSWY3DPEHPK3PXP"

    rotated = both.rotate(sealed)
    assert rotated is not None
    assert totp.SecretBox([new]).open(rotated) == "JBSWY3DPEHPK3PXP"
    assert totp.SecretBox([old]).open(rotated) is None
    assert totp.SecretBox([new]).rotate(sealed) is None  # no key opens it


def test_keys_are_read_in_order_and_must_be_long(monkeypatch: pytest.MonkeyPatch) -> None:
    first, second = "a" * 32, "b" * 40
    monkeypatch.setenv("MFA_ENCRYPTION_KEYS", f" {first} , {second} ,")
    assert Settings(_env_file=None).mfa_keys == [first, second]

    monkeypatch.setenv("MFA_ENCRYPTION_KEYS", f"{first},too-short")
    with pytest.raises(ValidationError, match="MFA_ENCRYPTION_KEYS"):
        Settings(_env_file=None)

    monkeypatch.setenv("MFA_ENCRYPTION_KEYS", "")
    assert Settings(_env_file=None).mfa_keys == []


async def test_existing_secrets_keep_working_and_move_to_the_new_key(
    app: FastAPI, customer: ApiUser, make_client: MakeClient, swap_settings: SwapSettings
) -> None:
    secret, _codes = await _turn_on(customer)  # sealed with the key derived from JWT_SECRET_KEY
    old_jwt = app.state.settings.jwt_secret
    new_key = secrets.token_urlsafe(32)
    with_key = app.state.settings.model_copy(update={"mfa_encryption_keys": SecretStr(new_key)})
    swap_settings(with_key)

    # Setting MFA_ENCRYPTION_KEYS does not lock anybody out: the old key still opens the secret.
    client = make_client()
    token = await _password_step(client, customer)
    next_code = totp.code_at(
        secret, now=time.time() + totp.STEP_SECONDS
    )  # turning on used this one
    signed_in = await client.post(
        f"{API}/auth/login/mfa", json={"mfa_token": token, "code": next_code}
    )
    assert signed_in.status_code == 200, signed_in.text

    stranger = totp.SecretBox([secrets.token_urlsafe(32)]).seal("NOT-OURS")
    async with app.state.db.sessionmaker() as session:
        user: User | None = await session.get(User, uuid.UUID(customer.id))
        assert user is not None
        user.mfa_pending_secret = stranger  # sealed with a key the server does not have
        await session.commit()

        result = await mfa.rotate_keys(session, with_key)
        assert result == mfa.Rotation(rotated=1, unreadable=1)

        await session.refresh(user)
        assert user.mfa_secret is not None
        # Only the new key opens it now, so JWT_SECRET_KEY can change without losing it.
        assert totp.SecretBox([new_key]).open(user.mfa_secret) == secret
        assert totp.SecretBox([old_jwt]).open(user.mfa_secret) is None
        assert user.mfa_pending_secret == stranger  # left alone
        user.mfa_last_step = None  # as if a minute had passed, so a fresh code is accepted
        await session.commit()

    # With a different JWT_SECRET_KEY the reader still signs in with the next code.
    moved = with_key.model_copy(update={"jwt_secret_key": SecretStr(secrets.token_urlsafe(64))})
    swap_settings(moved)
    client = make_client()
    token = await _password_step(client, customer)
    again = await client.post(
        f"{API}/auth/login/mfa", json={"mfa_token": token, "code": totp.code_at(secret)}
    )
    assert again.status_code == 200, again.text
