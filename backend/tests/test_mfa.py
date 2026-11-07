from __future__ import annotations

import time

from httpx import AsyncClient

from app.core import totp
from tests.conftest import API, PASSWORD, ApiUser, RegisterUser

STEP = totp.STEP_SECONDS


async def _turn_on(user: ApiUser) -> tuple[str, list[str]]:
    setup = await user.post(f"{API}/users/me/mfa/setup", json={"password": PASSWORD})
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    enabled = await user.post(f"{API}/users/me/mfa/enable", json={"code": totp.code_at(secret)})
    assert enabled.status_code == 200, enabled.text
    codes: list[str] = enabled.json()["recovery_codes"]
    return secret, codes


async def _password_step(client: AsyncClient, user: ApiUser) -> str:
    response = await client.post(
        f"{API}/auth/login", json={"email": user.email, "password": PASSWORD}
    )
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "MFA_REQUIRED"
    token: str = response.json()["error"]["details"]["mfa_token"]
    return token


def test_codes_follow_rfc_6238() -> None:
    # Test vector from RFC 6238 (SHA-1, T = 59 s), last six digits.
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # "12345678901234567890"
    assert totp.code_at(secret, now=59) == "287082"
    assert totp.matching_step(secret, "287082", now=59 + STEP) == 1  # one step late is fine
    assert totp.matching_step(secret, "287082", now=59 + 3 * STEP) is None


async def test_turning_it_on_and_signing_in_with_a_code(
    customer: ApiUser, make_client: object
) -> None:
    wrong = await customer.post(f"{API}/users/me/mfa/setup", json={"password": "not-it-at-all"})
    assert wrong.json()["error"]["code"] == "INVALID_CURRENT_PASSWORD"
    setup = (await customer.post(f"{API}/users/me/mfa/setup", json={"password": PASSWORD})).json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/Little%20Dragon%3A")
    bad = await customer.post(f"{API}/users/me/mfa/enable", json={"code": "000000"})
    assert bad.json()["error"]["code"] == "INVALID_MFA_CODE"
    secret = setup["secret"]
    enabled = await customer.post(f"{API}/users/me/mfa/enable", json={"code": totp.code_at(secret)})
    codes = enabled.json()["recovery_codes"]
    assert len(codes) == 10
    assert (await customer.get(f"{API}/users/me")).json()["mfa_enabled"] is True

    client = make_client()  # type: ignore[operator]
    token = await _password_step(client, customer)
    # The code used to turn it on cannot be used again; the next one works.
    replay = await client.post(
        f"{API}/auth/login/mfa", json={"mfa_token": token, "code": totp.code_at(secret)}
    )
    assert replay.json()["error"]["code"] == "INVALID_MFA_CODE"
    signed_in = await client.post(
        f"{API}/auth/login/mfa",
        json={"mfa_token": token, "code": totp.code_at(secret, time.time() + STEP)},
    )
    assert signed_in.status_code == 200, signed_in.text
    assert signed_in.json()["user"]["email"] == customer.email
    assert "refresh_token" in signed_in.cookies

    # A recovery code works once.
    token = await _password_step(client, customer)
    first = await client.post(f"{API}/auth/login/mfa", json={"mfa_token": token, "code": codes[0]})
    assert first.status_code == 200
    token = await _password_step(client, customer)
    again = await client.post(f"{API}/auth/login/mfa", json={"mfa_token": token, "code": codes[0]})
    assert again.status_code == 401
    forged = await client.post(
        f"{API}/auth/login/mfa", json={"mfa_token": token + "x", "code": codes[1]}
    )
    assert forged.json()["error"]["code"] == "MFA_TOKEN_INVALID"

    off = await customer.post(f"{API}/users/me/mfa/disable", json={"password": PASSWORD})
    assert off.status_code == 204
    plain = await client.post(
        f"{API}/auth/login", json={"email": customer.email, "password": PASSWORD}
    )
    assert plain.status_code == 200


async def test_the_library_can_require_it_for_staff(
    admin: ApiUser, register_user: RegisterUser, make_client: object
) -> None:
    # The administrator turns it on for themselves first.
    first = await admin.patch(f"{API}/admin/settings", json={"require_staff_mfa": True})
    assert first.json()["error"]["code"] == "MFA_SETUP_REQUIRED_FIRST"
    await _turn_on(admin)
    required = await admin.patch(f"{API}/admin/settings", json={"require_staff_mfa": True})
    assert required.status_code == 200, required.text
    assert required.json()["require_staff_mfa"] is True

    staff = await register_user(email="desk@example.com")
    await admin.patch(f"{API}/admin/users/{staff.id}", json={"role": "librarian"})
    blocked = await staff.get(f"{API}/admin/books")
    assert blocked.json()["error"]["code"] == "MFA_SETUP_REQUIRED"
    _, codes = await _turn_on(staff)
    assert (await staff.get(f"{API}/admin/books")).status_code == 200
    kept = await staff.post(f"{API}/users/me/mfa/disable", json={"password": PASSWORD})
    assert kept.json()["error"]["code"] == "MFA_REQUIRED_BY_LIBRARY"

    # Lost the phone and the codes: an administrator resets it.
    reset = await admin.patch(f"{API}/admin/users/{staff.id}", json={"reset_mfa": True})
    assert reset.json()["mfa_enabled"] is False
    assert len(codes) == 10
