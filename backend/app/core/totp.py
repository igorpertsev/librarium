"""Time-based one-time passwords (RFC 6238: HMAC-SHA1, 6 digits, 30-second steps), as used by
authenticator apps, and encryption of the shared secrets at rest."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

STEP_SECONDS = 30
DIGITS = 6
# Codes from one step before or after are accepted too (clocks drift a little).
WINDOW = 1
ISSUER = "Little Dragon"


def new_secret() -> str:
    """A random 160-bit secret in base32, as authenticator apps expect it."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret: str, step: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(number % 10**DIGITS).zfill(DIGITS)


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // STEP_SECONDS)


def code_at(secret: str, now: float | None = None) -> str:
    return _code(secret, current_step(now))


def matching_step(
    secret: str, code: str, *, now: float | None = None, after: int | None = None
) -> int | None:
    """The time step the code belongs to, or None. Steps up to ``after`` (already used) are
    refused, so a code cannot be replayed."""
    code = code.strip().replace(" ", "")
    if not (code.isdigit() and len(code) == DIGITS):
        return None
    step = current_step(now)
    for candidate in range(step - WINDOW, step + WINDOW + 1):
        if after is not None and candidate <= after:
            continue
        if hmac.compare_digest(_code(secret, candidate), code):
            return candidate
    return None


def provisioning_uri(secret: str, account: str) -> str:
    """otpauth:// link for the QR code an authenticator app scans."""
    label = quote(f"{ISSUER}:{account}")
    query = urlencode(
        {"secret": secret, "issuer": ISSUER, "digits": DIGITS, "period": STEP_SECONDS}
    )
    return f"otpauth://totp/{label}?{query}"


# --- Recovery codes ------------------------------------------------------------------------

RECOVERY_CODES = 10
_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o, 1/l/i


def new_recovery_codes() -> list[str]:
    def one() -> str:
        chars = "".join(secrets.choice(_ALPHABET) for _ in range(10))
        return f"{chars[:5]}-{chars[5:]}"

    return [one() for _ in range(RECOVERY_CODES)]


def hash_recovery_code(code: str) -> str:
    """High-entropy random codes: a plain SHA-256 is enough (no password-style hashing)."""
    normalized = code.strip().lower().replace("-", "").replace(" ", "")
    return hashlib.sha256(normalized.encode()).hexdigest()


# --- Secrets at rest ------------------------------------------------------------------------


class SecretBox:
    """Encrypts TOTP secrets with a key derived from the server secret (HKDF-SHA256)."""

    def __init__(self, server_secret: str) -> None:
        key = HKDF(
            algorithm=hashes.SHA256(), length=32, salt=None, info=b"librarium-totp-secrets"
        ).derive(server_secret.encode())
        self._fernet = Fernet(base64.urlsafe_b64encode(key))

    def seal(self, secret: str) -> str:
        return self._fernet.encrypt(secret.encode()).decode()

    def open(self, sealed: str) -> str | None:
        try:
            return self._fernet.decrypt(sealed.encode()).decode()
        except InvalidToken:
            return None  # the server secret changed: the user has to set it up again
