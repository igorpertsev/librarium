from __future__ import annotations

import hashlib
import uuid

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from app.models import RefreshToken
from tests.conftest import API, FRONTEND_ORIGIN, PASSWORD, ApiUser, MakeClient, RegisterUser

REGISTER = f"{API}/auth/register"
LOGIN = f"{API}/auth/login"
REFRESH = f"{API}/auth/refresh"
LOGOUT = f"{API}/auth/logout"
ME = f"{API}/auth/me"


def _cookie_header(token: str) -> dict[str, str]:
    return {"Cookie": f"refresh_token={token}"}


async def test_register_returns_access_token_and_sets_http_only_cookie(client: AsyncClient) -> None:
    response = await client.post(
        REGISTER,
        json={
            "email": "  New.Reader@Example.COM ",
            "password": PASSWORD,
            "full_name": "New Reader",
            "whatsapp": "+1 234 567 8900",
            "preferred_contact_method": "whatsapp",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["expires_in"] == 15 * 60
    assert body["user"]["email"] == "new.reader@example.com"
    assert body["user"]["role"] == "customer"
    assert "password" not in response.text
    assert "password_hash" not in body["user"]
    assert "refresh_token" not in body

    set_cookie = response.headers["set-cookie"].lower()
    assert "refresh_token=" in set_cookie
    assert "httponly" in set_cookie
    assert "path=/api/v1/auth" in set_cookie
    assert "samesite=lax" in set_cookie
    assert "max-age=" in set_cookie


async def test_register_rejects_duplicate_email_case_insensitively(
    client: AsyncClient, register_user: RegisterUser
) -> None:
    await register_user(email="dup@example.com")
    response = await client.post(
        REGISTER,
        json={
            "email": "DUP@example.com",
            "password": PASSWORD,
            "full_name": "Copy",
            "telegram": "@copy",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"


async def test_register_cannot_choose_role_and_requires_a_contact(client: AsyncClient) -> None:
    base = {"email": "x@example.com", "password": PASSWORD, "full_name": "X"}
    sneaky = await client.post(REGISTER, json={**base, "telegram": "@x", "role": "admin"})
    assert sneaky.status_code == 422  # unknown fields are rejected, role is server-side only

    no_contact = await client.post(REGISTER, json=base)
    assert no_contact.status_code == 422
    assert no_contact.json()["error"]["code"] == "VALIDATION_ERROR"

    short_password = await client.post(
        REGISTER, json={**base, "password": "Qz7#k", "telegram": "@x"}
    )
    assert short_password.status_code == 422
    assert "Qz7#k" not in short_password.text  # submitted values are not echoed back


async def test_login_and_me(client: AsyncClient, customer: ApiUser) -> None:
    response = await client.post(LOGIN, json={"email": customer.email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]

    me = await client.get(ME, headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["id"] == customer.id

    users_me = await client.get(f"{API}/users/me", headers={"Authorization": f"Bearer {token}"})
    assert users_me.status_code == 200
    assert users_me.json() == me.json()


async def test_login_errors_do_not_reveal_whether_email_exists(
    client: AsyncClient, customer: ApiUser
) -> None:
    wrong_password = await client.post(LOGIN, json={"email": customer.email, "password": "nope!"})
    unknown_email = await client.post(
        LOGIN, json={"email": "ghost@example.com", "password": "nope!"}
    )
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert wrong_password.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_me_requires_valid_token(client: AsyncClient) -> None:
    missing = await client.get(ME)
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "NOT_AUTHENTICATED"

    garbage = await client.get(ME, headers={"Authorization": "Bearer not-a-jwt"})
    assert garbage.status_code == 401
    assert garbage.json()["error"]["code"] == "INVALID_TOKEN"


async def test_refresh_rotates_token_and_old_token_stops_working(
    make_client: MakeClient, customer: ApiUser
) -> None:
    first = customer.refresh_token
    assert first

    rotated = await customer.client.post(REFRESH)
    assert rotated.status_code == 200, rotated.text
    second = rotated.cookies.get("refresh_token")
    assert second
    assert second != first
    assert rotated.json()["access_token"] != customer.access_token

    me = await customer.client.get(
        ME, headers={"Authorization": f"Bearer {rotated.json()['access_token']}"}
    )
    assert me.status_code == 200

    # The rotated-away token is rejected (and treated as reuse).
    stale = await make_client().post(REFRESH, headers=_cookie_header(first))
    assert stale.status_code == 401
    assert stale.json()["error"]["code"] == "REFRESH_TOKEN_REUSED"


async def test_refresh_token_reuse_revokes_whole_family(
    app: FastAPI, make_client: MakeClient, customer: ApiUser
) -> None:
    first = customer.refresh_token
    assert first
    second = (await customer.client.post(REFRESH)).cookies.get("refresh_token")
    assert second

    attacker = await make_client().post(REFRESH, headers=_cookie_header(first))
    assert attacker.status_code == 401
    assert attacker.json()["error"]["code"] == "REFRESH_TOKEN_REUSED"

    # The legitimate (latest) token of the same family is now dead too.
    victim = await make_client().post(REFRESH, headers=_cookie_header(second))
    assert victim.status_code == 401

    async with app.state.db.sessionmaker() as session:
        tokens = (
            await session.scalars(
                select(RefreshToken).where(RefreshToken.user_id == uuid.UUID(customer.id))
            )
        ).all()
    assert len(tokens) == 2
    assert len({t.family_id for t in tokens}) == 1
    assert all(t.revoked_at is not None for t in tokens)


async def test_refresh_without_cookie_is_401(client: AsyncClient) -> None:
    response = await client.post(REFRESH)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "REFRESH_TOKEN_MISSING"


async def test_logout_revokes_refresh_token_and_clears_cookie(
    make_client: MakeClient, customer: ApiUser
) -> None:
    token = customer.refresh_token
    assert token
    response = await customer.client.post(LOGOUT)
    assert response.status_code == 204
    assert 'refresh_token=""' in response.headers["set-cookie"] or "max-age=0" in (
        response.headers["set-cookie"].lower()
    )

    after = await make_client().post(REFRESH, headers=_cookie_header(token))
    assert after.status_code == 401


async def test_refresh_tokens_are_stored_hashed(app: FastAPI, customer: ApiUser) -> None:
    raw = customer.refresh_token
    assert raw
    async with app.state.db.sessionmaker() as session:
        stored = (await session.scalars(select(RefreshToken.token_hash))).all()
    assert raw not in stored
    assert hashlib.sha256(raw.encode()).hexdigest() in stored


async def test_disabled_user_cannot_log_in_or_use_tokens(
    make_client: MakeClient, customer: ApiUser, admin: ApiUser
) -> None:
    disable = await admin.patch(f"{API}/admin/users/{customer.id}", json={"is_active": False})
    assert disable.status_code == 200, disable.text

    login = await make_client().post(LOGIN, json={"email": customer.email, "password": PASSWORD})
    assert login.status_code == 403
    assert login.json()["error"]["code"] == "ACCOUNT_DISABLED"

    old_access = await customer.get(ME)
    assert old_access.status_code == 401
    assert old_access.json()["error"]["code"] == "ACCOUNT_DISABLED"

    old_refresh = await customer.client.post(REFRESH)
    assert old_refresh.status_code == 401


async def test_change_password_signs_out_other_sessions(
    make_client: MakeClient, customer: ApiUser
) -> None:
    other_device_token = customer.refresh_token
    assert other_device_token

    wrong = await customer.post(
        f"{API}/auth/change-password",
        json={"current_password": "wrong-password", "new_password": "new-password-123"},
    )
    assert wrong.status_code == 400
    assert wrong.json()["error"]["code"] == "INVALID_CURRENT_PASSWORD"

    changed = await customer.post(
        f"{API}/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "new-password-123"},
    )
    assert changed.status_code == 200, changed.text

    revoked = await make_client().post(REFRESH, headers=_cookie_header(other_device_token))
    assert revoked.status_code == 401

    fresh = make_client()
    old_login = await fresh.post(LOGIN, json={"email": customer.email, "password": PASSWORD})
    assert old_login.status_code == 401
    new_login = await fresh.post(
        LOGIN, json={"email": customer.email, "password": "new-password-123"}
    )
    assert new_login.status_code == 200


async def test_cookie_endpoints_reject_foreign_origin(customer: ApiUser) -> None:
    evil = await customer.client.post(REFRESH, headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403
    assert evil.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"

    allowed = await customer.client.post(REFRESH, headers={"Origin": FRONTEND_ORIGIN})
    assert allowed.status_code == 200


async def test_profile_patch_distinguishes_missing_and_null(customer: ApiUser) -> None:
    # Omitted fields are untouched; null clears a nullable contact.
    response = await customer.patch(
        f"{API}/users/me",
        json={"whatsapp": "+44 20 7946 0958", "preferred_contact_method": "whatsapp"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["telegram"] == "@reader"
    assert body["whatsapp"] == "+44 20 7946 0958"

    cleared = await customer.patch(f"{API}/users/me", json={"telegram": None})
    assert cleared.status_code == 200
    assert cleared.json()["telegram"] is None
    assert cleared.json()["full_name"] == "Charlie Customer"

    null_name = await customer.patch(f"{API}/users/me", json={"full_name": None})
    assert null_name.status_code == 422

    dangling_preference = await customer.patch(
        f"{API}/users/me", json={"preferred_contact_method": "instagram"}
    )
    assert dangling_preference.status_code == 422


async def test_profile_email_change_conflict(customer: ApiUser, other_customer: ApiUser) -> None:
    response = await customer.patch(f"{API}/users/me", json={"email": other_customer.email})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"
