from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import select

from app.core import totp
from app.core.config import Settings
from app.main import create_app
from app.models import UserIdentity
from app.services import oauth
from tests.conftest import API, PASSWORD, ApiUser, make_settings

GOOGLE_ID = "google-client.apps.example"
APPLE_ID = "com.example.library.web"
RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
APPLE_TEAM_KEY = ec.generate_private_key(ec.SECP256R1())


class FakeProviders:
    """Google's and Apple's token and key endpoints, answering like the real ones."""

    def __init__(self) -> None:
        self.claims: dict[str, Any] = {}
        self.token_requests: list[dict[str, list[str]]] = []

    def id_token(self, issuer: str, audience: str) -> str:
        now = int(time.time())
        claims = {"iss": issuer, "aud": audience, "iat": now, "exp": now + 600, **self.claims}
        return jwt.encode(claims, RSA_KEY, algorithm="RS256", headers={"kid": "k1"})

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith(("/oauth2/v3/certs", "/auth/keys")):
            jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(RSA_KEY.public_key()))
            return httpx.Response(200, json={"keys": [{**jwk, "kid": "k1", "alg": "RS256"}]})
        form = parse_qs(request.content.decode())
        self.token_requests.append(form)
        if url == "https://oauth2.googleapis.com/token":
            assert form["client_secret"] == ["google-secret"]
            return httpx.Response(
                200, json={"id_token": self.id_token("https://accounts.google.com", GOOGLE_ID)}
            )
        if url == "https://appleid.apple.com/auth/token":
            # Apple's client secret is a JWT signed with the team's key.
            jwt.decode(
                form["client_secret"][0],
                APPLE_TEAM_KEY.public_key(),
                algorithms=["ES256"],
                audience="https://appleid.apple.com",
            )
            return httpx.Response(
                200, json={"id_token": self.id_token("https://appleid.apple.com", APPLE_ID)}
            )
        return httpx.Response(404)


@pytest.fixture
async def social(database_url: str) -> AsyncIterator[tuple[FastAPI, FakeProviders]]:
    pem = APPLE_TEAM_KEY.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    settings = make_settings(
        database_url,
        api_public_url="http://testserver/api/v1",
        google_client_id=GOOGLE_ID,
        google_client_secret=SecretStr("google-secret"),
        apple_client_id=APPLE_ID,
        apple_team_id="TEAM123456",
        apple_key_id="KEY1234567",
        apple_private_key=SecretStr(pem),
        rate_limit_enabled=False,
    )
    application = create_app(settings)
    fake = FakeProviders()
    await application.state.http.aclose()
    application.state.http = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))
    oauth._jwks_cache.clear()
    yield application, fake
    await application.state.http.aclose()
    await application.state.db.dispose()


def _browser(application: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=application), base_url="http://testserver")


async def _start(
    browser: AsyncClient, provider: str, next_path: str = "/profile"
) -> dict[str, str]:
    started = await browser.get(f"{API}/auth/oauth/{provider}/start", params={"next": next_path})
    assert started.status_code == 302, started.text
    query = parse_qs(urlsplit(started.headers["location"]).query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["redirect_uri"] == [f"http://testserver/api/v1/auth/oauth/{provider}/callback"]
    return {key: values[0] for key, values in query.items()}


async def test_google_sign_in_creates_then_finds_the_account(
    social: tuple[FastAPI, FakeProviders],
) -> None:
    application, fake = social
    async with _browser(application) as browser:
        assert (await browser.get(f"{API}/auth/oauth/providers")).json() == {
            "providers": ["google", "apple"]
        }
        query = await _start(browser, "google", "/profile")
        fake.claims = {
            "sub": "g-123",
            "email": "New.Reader@Example.com",
            "email_verified": True,
            "nonce": query["nonce"],
            "name": "New Reader",
        }
        back = await browser.get(
            f"{API}/auth/oauth/google/callback", params={"state": query["state"], "code": "c1"}
        )
        assert back.status_code == 303
        assert back.headers["location"] == "http://localhost:5173/profile"
        assert "refresh_token" in back.cookies
        assert fake.token_requests[0]["code_verifier"][0]  # PKCE
        session = await browser.post(f"{API}/auth/refresh")
        assert session.json()["user"]["email"] == "new.reader@example.com"
        assert session.json()["user"]["full_name"] == "New Reader"

        # Again: the same account, by Google's subject id.
        query = await _start(browser, "google")
        fake.claims["nonce"] = query["nonce"]
        await browser.get(
            f"{API}/auth/oauth/google/callback", params={"state": query["state"], "code": "c2"}
        )
    async with application.state.db.sessionmaker() as db:
        identities = (await db.scalars(select(UserIdentity))).all()
    assert [(i.provider, i.subject) for i in identities] == [("google", "g-123")]


async def test_existing_accounts_are_linked_by_verified_email_and_keep_two_step_sign_in(
    social: tuple[FastAPI, FakeProviders], customer: ApiUser
) -> None:
    application, fake = social
    async with _browser(application) as browser:
        query = await _start(browser, "google")
        fake.claims = {
            "sub": "g-9",
            "email": customer.email,
            "email_verified": "true",
            "nonce": query["nonce"],
        }
        back = await browser.get(
            f"{API}/auth/oauth/google/callback", params={"state": query["state"], "code": "c"}
        )
        assert back.headers["location"] == "http://localhost:5173/profile"
        me = await browser.post(f"{API}/auth/refresh")
        assert me.json()["user"]["id"] == customer.id

    # With two-step sign-in on, the code is still asked for on the sign-in page.
    setup = await customer.post(f"{API}/users/me/mfa/setup", json={"password": PASSWORD})
    await customer.post(
        f"{API}/users/me/mfa/enable", json={"code": totp.code_at(setup.json()["secret"])}
    )
    async with _browser(application) as browser:
        query = await _start(browser, "google")
        fake.claims["nonce"] = query["nonce"]
        back = await browser.get(
            f"{API}/auth/oauth/google/callback", params={"state": query["state"], "code": "c"}
        )
        assert back.headers["location"].startswith("http://localhost:5173/login#mfa=")
        assert "refresh_token" not in back.cookies


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"state": "forged"}, "OAUTH_STATE"),
        ({"nonce": "other"}, "OAUTH_FAILED"),
        ({"email_verified": False}, "OAUTH_NO_EMAIL"),
        ({"error": "access_denied"}, "OAUTH_CANCELLED"),
    ],
)
async def test_failed_sign_ins_go_back_to_the_sign_in_page_with_a_reason(
    social: tuple[FastAPI, FakeProviders], change: dict[str, Any], error: str
) -> None:
    application, fake = social
    async with _browser(application) as browser:
        query = await _start(browser, "google")
        fake.claims = {
            "sub": f"g-{uuid.uuid4()}",
            "email": "someone@example.com",
            "email_verified": change.get("email_verified", True),
            "nonce": change.get("nonce", query["nonce"]),
        }
        params = {"state": change.get("state", query["state"]), "code": "c"}
        if "error" in change:
            params = {"state": query["state"], "error": change["error"]}
        back = await browser.get(f"{API}/auth/oauth/google/callback", params=params)
        assert back.headers["location"] == f"http://localhost:5173/login?oauth_error={error}"
        assert "refresh_token" not in back.cookies


async def test_apple_posts_back_and_sends_the_name_once(
    social: tuple[FastAPI, FakeProviders],
) -> None:
    application, fake = social
    async with _browser(application) as browser:
        query = await _start(browser, "apple", "//evil.example.com")
        assert query["response_mode"] == "form_post"
        fake.claims = {
            "sub": "a-1",
            "email": "hidden@privaterelay.appleid.com",
            "email_verified": "true",
            "nonce": query["nonce"],
        }
        back = await browser.post(
            f"{API}/auth/oauth/apple/callback",
            data={
                "state": query["state"],
                "code": "c",
                "user": json.dumps({"name": {"firstName": "Ada", "lastName": "Lovelace"}}),
            },
        )
        assert back.headers["location"] == "http://localhost:5173/"  # never another site
        me = await browser.post(f"{API}/auth/refresh")
        assert me.json()["user"]["full_name"] == "Ada Lovelace"


async def test_no_providers_without_credentials(client: AsyncClient) -> None:
    assert (await client.get(f"{API}/auth/oauth/providers")).json() == {"providers": []}
    refused = await client.get(f"{API}/auth/oauth/google/start")
    assert refused.json()["error"]["code"] == "OAUTH_NOT_CONFIGURED"


def test_an_apple_key_written_on_one_line_works() -> None:
    pem = APPLE_TEAM_KEY.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    one_line = pem.replace("\n", "\\n")
    settings = Settings(_env_file=None, apple_private_key=one_line)  # type: ignore[call-arg]
    assert settings.apple_private_key is not None
    assert settings.apple_private_key.get_secret_value() == pem
