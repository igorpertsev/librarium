"""Passkeys (WebAuthn), checked with a software authenticator that signs like a real one."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import uuid
from typing import Any

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import update

from app.models import LibrarySettings, User
from app.models.enums import UserRole
from tests.conftest import API, FRONTEND_ORIGIN, PASSWORD, ApiUser, MakeClient


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


class SoftAuthenticator:
    """A passkey on a pretend device: P-256 key, "none" attestation, user verified."""

    def __init__(self, origin: str = FRONTEND_ORIGIN, rp_id: str = "localhost") -> None:
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(32)
        self.origin = origin
        self.rp_hash = hashlib.sha256(rp_id.encode()).digest()
        self.count = 0

    def _client_data(self, kind: str, options: dict[str, Any]) -> bytes:
        return json.dumps(
            {
                "type": kind,
                "challenge": options["challenge"],
                "origin": self.origin,
                "crossOrigin": False,
            }
        ).encode()

    def create(self, options: dict[str, Any]) -> dict[str, Any]:
        numbers = self.key.public_key().public_numbers()
        cose = cbor2.dumps(
            {
                1: 2,
                3: -7,
                -1: 1,
                -2: numbers.x.to_bytes(32, "big"),
                -3: numbers.y.to_bytes(32, "big"),
            }
        )
        auth_data = (
            self.rp_hash
            + bytes([0x45])  # user present, user verified, attested credential data
            + self.count.to_bytes(4, "big")
            + bytes(16)  # AAGUID
            + len(self.credential_id).to_bytes(2, "big")
            + self.credential_id
            + cose
        )
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {
            "id": b64url(self.credential_id),
            "rawId": b64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64url(self._client_data("webauthn.create", options)),
                "attestationObject": b64url(attestation),
                "transports": ["internal"],
            },
            "clientExtensionResults": {},
        }

    def get(self, options: dict[str, Any], *, verified: bool = True) -> dict[str, Any]:
        self.count += 1
        client_data = self._client_data("webauthn.get", options)
        auth_data = (
            self.rp_hash + bytes([0x05 if verified else 0x01]) + self.count.to_bytes(4, "big")
        )
        signature = self.key.sign(
            auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256())
        )
        return {
            "id": b64url(self.credential_id),
            "rawId": b64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64url(client_data),
                "authenticatorData": b64url(auth_data),
                "signature": b64url(signature),
                "userHandle": None,
            },
            "clientExtensionResults": {},
        }


async def _add(user: ApiUser, device: SoftAuthenticator, name: str = "Phone") -> Any:
    started = await user.post(f"{API}/users/me/passkeys/options", json={"password": PASSWORD})
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["options"]["authenticatorSelection"]["userVerification"] == "required"
    return await user.post(
        f"{API}/users/me/passkeys",
        json={"state": body["state"], "credential": device.create(body["options"]), "name": name},
    )


async def _sign_in(client: AsyncClient, device: SoftAuthenticator, **kwargs: Any) -> Any:
    started = (await client.post(f"{API}/auth/passkey/options")).json()
    return await client.post(
        f"{API}/auth/passkey",
        json={"state": started["state"], "credential": device.get(started["options"], **kwargs)},
    )


async def test_a_reader_adds_a_passkey_and_signs_in_with_it(
    customer: ApiUser, make_client: MakeClient
) -> None:
    wrong = await customer.post(f"{API}/users/me/passkeys/options", json={"password": "nope-nope"})
    assert wrong.json()["error"]["code"] == "INVALID_CURRENT_PASSWORD"

    phone = SoftAuthenticator()
    added = await _add(customer, phone)
    assert added.status_code == 201, added.text
    assert added.json()["name"] == "Phone"
    again = await _add(customer, phone)  # the same credential twice
    assert (again.status_code, again.json()["error"]["code"]) == (409, "PASSKEY_EXISTS")

    client = make_client()
    signed_in = await _sign_in(client, phone)
    assert signed_in.status_code == 200, signed_in.text
    assert signed_in.json()["user"]["id"] == customer.id
    assert "refresh_token" in signed_in.cookies
    listed = (await customer.get(f"{API}/users/me/passkeys")).json()
    assert [(p["name"], p["last_used_at"] is not None) for p in listed] == [("Phone", True)]

    assert (await customer.delete(f"{API}/users/me/passkeys/{listed[0]['id']}")).status_code == 204
    assert (await _sign_in(make_client(), phone)).json()["error"]["code"] == "PASSKEY_UNKNOWN"


async def test_bad_answers_are_refused(
    app: FastAPI, customer: ApiUser, other_customer: ApiUser, make_client: MakeClient
) -> None:
    phone = SoftAuthenticator()
    assert (await _add(customer, phone)).status_code == 201
    client = make_client()

    unverified = await _sign_in(client, phone, verified=False)  # no Face ID / PIN on the device
    assert unverified.json()["error"]["code"] == "PASSKEY_INVALID"

    phishing = SoftAuthenticator(origin="https://evil.example")
    phishing.key, phishing.credential_id = phone.key, phone.credential_id
    assert (await _sign_in(client, phishing)).json()["error"]["code"] == "PASSKEY_INVALID"

    started = (await client.post(f"{API}/auth/passkey/options")).json()
    answer = phone.get(started["options"])
    answer["response"]["signature"] = b64url(b"\x30\x06\x02\x01\x01\x02\x01\x01")
    forged = await client.post(
        f"{API}/auth/passkey", json={"state": started["state"], "credential": answer}
    )
    assert forged.json()["error"]["code"] == "PASSKEY_INVALID"

    # A state from adding a passkey cannot be used to sign in.
    adding = (
        await customer.post(f"{API}/users/me/passkeys/options", json={"password": PASSWORD})
    ).json()
    swapped = await client.post(
        f"{API}/auth/passkey",
        json={"state": adding["state"], "credential": phone.get(adding["options"])},
    )
    assert swapped.json()["error"]["code"] == "PASSKEY_STATE"

    # Someone else's passkey cannot be removed.
    mine = (await customer.get(f"{API}/users/me/passkeys")).json()[0]["id"]
    assert (await other_customer.delete(f"{API}/users/me/passkeys/{mine}")).status_code == 404

    async with app.state.db.sessionmaker() as session:
        await session.execute(
            update(User).where(User.id == uuid.UUID(customer.id)).values(is_active=False)
        )
        await session.commit()
    disabled = await _sign_in(make_client(), phone)
    assert (disabled.status_code, disabled.json()["error"]["code"]) == (403, "ACCOUNT_DISABLED")


async def test_a_passkey_satisfies_two_step_sign_in_for_staff(
    app: FastAPI, customer: ApiUser
) -> None:
    async with app.state.db.sessionmaker() as session:
        await session.execute(
            update(User).where(User.id == uuid.UUID(customer.id)).values(role=UserRole.LIBRARIAN)
        )
        await session.execute(update(LibrarySettings).values(require_staff_mfa=True))
        await session.commit()
    refused = await customer.get(f"{API}/admin/books")
    assert refused.json()["error"]["code"] == "MFA_SETUP_REQUIRED"
    assert (await _add(customer, SoftAuthenticator(), "Laptop")).status_code == 201
    assert (await customer.get(f"{API}/admin/books")).status_code == 200
