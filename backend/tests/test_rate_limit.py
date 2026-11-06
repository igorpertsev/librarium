from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.rate_limit import (
    LOGIN_FAILURES_PER_EMAIL,
    PASSWORD_FAILURES_PER_USER,
    REGISTER_PER_IP,
    Limit,
    RateLimiter,
    TooManyRequestsError,
)
from tests.conftest import API, FRONTEND_ORIGIN, PASSWORD, ApiUser, MakeClient


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_sliding_window_allows_again_after_the_period() -> None:
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    limit = Limit(3, 60)
    for _ in range(3):
        limiter.consume("k", limit)
    with pytest.raises(TooManyRequestsError) as error:
        limiter.consume("k", limit)
    assert error.value.details == {"retry_after": 60}
    assert error.value.headers == {"Retry-After": "60"}

    clock.now += 30
    with pytest.raises(TooManyRequestsError) as error:
        limiter.check("k", limit)
    assert error.value.details == {"retry_after": 30}

    clock.now += 30  # the first hits have left the window
    limiter.consume("k", limit)
    limiter.consume("other", limit)  # keys are independent


def test_disabled_limiter_and_key_eviction() -> None:
    disabled = RateLimiter(enabled=False)
    for _ in range(10):
        disabled.consume("k", Limit(1, 60))

    clock = FakeClock()
    small = RateLimiter(clock=clock, max_keys=2)
    small.hit("a", Limit(1, 60))
    small.hit("b", Limit(1, 60))
    small.hit("c", Limit(1, 60))  # evicts the oldest key
    small.check("a", Limit(1, 60))
    with pytest.raises(TooManyRequestsError):
        small.check("c", Limit(1, 60))


async def _login(client: AsyncClient, email: str, password: str) -> int:
    response = await client.post(
        f"{API}/auth/login",
        json={"email": email, "password": password},
        headers={"Origin": FRONTEND_ORIGIN},
    )
    return response.status_code


async def test_failed_logins_lock_the_email_for_a_while(
    client: AsyncClient, customer: ApiUser
) -> None:
    for _ in range(LOGIN_FAILURES_PER_EMAIL.attempts):
        assert await _login(client, customer.email, "wrong-password-123") == 401

    response = await client.post(
        f"{API}/auth/login", json={"email": customer.email, "password": PASSWORD}
    )
    assert response.status_code == 429  # even the right password, until the window passes
    body = response.json()["error"]
    assert body["code"] == "TOO_MANY_REQUESTS"
    assert body["details"]["retry_after"] > 0
    assert int(response.headers["Retry-After"]) == body["details"]["retry_after"]

    # Other accounts are not affected; the email is matched case-insensitively.
    assert await _login(client, "someone-else@example.com", "wrong-password-123") == 401
    assert await _login(client, customer.email.upper(), PASSWORD) == 429


async def test_successful_login_clears_failed_attempts(
    client: AsyncClient, customer: ApiUser
) -> None:
    for _ in range(LOGIN_FAILURES_PER_EMAIL.attempts - 1):
        assert await _login(client, customer.email, "wrong-password-123") == 401
    assert await _login(client, customer.email, PASSWORD) == 200
    for _ in range(LOGIN_FAILURES_PER_EMAIL.attempts - 1):
        assert await _login(client, customer.email, "wrong-password-123") == 401
    assert await _login(client, customer.email, PASSWORD) == 200


async def test_registrations_per_ip_are_limited(make_client: MakeClient) -> None:
    async def register(n: int) -> int:
        response = await make_client().post(
            f"{API}/auth/register",
            json={
                "email": f"new-{n}@example.com",
                "password": PASSWORD,
                "full_name": "New Reader",
                "telegram": "@new_reader",
            },
        )
        return response.status_code

    for n in range(REGISTER_PER_IP.attempts):
        assert await register(n) == 201
    assert await register(999) == 429


async def test_wrong_current_passwords_are_limited(customer: ApiUser) -> None:
    async def change(current: str) -> int:
        response = await customer.post(
            f"{API}/auth/change-password",
            json={"current_password": current, "new_password": "another-long-password"},
        )
        return response.status_code

    for _ in range(PASSWORD_FAILURES_PER_USER.attempts):
        assert await change("not-my-password") == 400
    assert await change(PASSWORD) == 429
