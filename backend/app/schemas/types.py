"""Reusable constrained field types."""

from __future__ import annotations

import re
from functools import cache
from typing import Annotated
from urllib.parse import urlparse
from zoneinfo import available_timezones

from pydantic import AfterValidator, BeforeValidator, EmailStr, StringConstraints

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def _blank_to_none(value: object) -> object:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _no_control_chars(value: str) -> str:
    if _CONTROL_CHARS.search(value):
        raise ValueError("must not contain control characters")
    return value


def _http_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("must be an absolute http(s) URL")
    return value


def _lower(value: str) -> str:
    return value.strip().lower()


NormalizedEmail = Annotated[EmailStr, StringConstraints(max_length=320), AfterValidator(_lower)]
# Login accepts any string so the endpoint is not an email-format oracle.
LoginEmail = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, max_length=320)]
# Passwords are never trimmed or otherwise altered.
Password = Annotated[str, StringConstraints(min_length=8, max_length=128)]
AnyPassword = Annotated[str, StringConstraints(min_length=1, max_length=128)]

FullName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
    AfterValidator(_no_control_chars),
]

_Phone = Annotated[str, StringConstraints(pattern=r"^\+?[0-9][0-9 ()\-.]{3,30}$")]
_Handle = Annotated[str, StringConstraints(max_length=100), AfterValidator(_no_control_chars)]
# Optional contact values: blank strings become ``null``.
PhoneLike = Annotated[_Phone | None, BeforeValidator(_blank_to_none)]
Handle = Annotated[_Handle | None, BeforeValidator(_blank_to_none)]

Title = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
    AfterValidator(_no_control_chars),
]
AuthorName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
    AfterValidator(_no_control_chars),
]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=10_000)]
AgeRange = Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)]
HttpUrlStr = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=2048), AfterValidator(_http_url)
]
OptionalHttpUrlStr = Annotated[HttpUrlStr | None, BeforeValidator(_blank_to_none)]

_UPLOADED_COVER = re.compile(r"^/media/covers/[0-9a-f]{32}-[SML]\.webp$")


def _image_url(value: str) -> str:
    """An absolute http(s) URL, or a cover uploaded to this server (/media/covers/...)."""
    return value if _UPLOADED_COVER.match(value) else _http_url(value)


ImageUrlStr = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=2048), AfterValidator(_image_url)
]
OptionalImageUrlStr = Annotated[ImageUrlStr | None, BeforeValidator(_blank_to_none)]
_Isbn = Annotated[str, StringConstraints(pattern=r"^[0-9Xx][0-9Xx\- ]{8,30}$")]
Isbn = Annotated[_Isbn | None, BeforeValidator(_blank_to_none)]
_Language = Annotated[str, StringConstraints(pattern=r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$")]
LanguageCode = Annotated[_Language | None, BeforeValidator(_blank_to_none)]
CurrencyCode = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Z]{3}$")]

PlaceName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
    AfterValidator(_no_control_chars),
]
Address = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
    AfterValidator(_no_control_chars),
]
_Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
OptionalNote = Annotated[_Note | None, BeforeValidator(_blank_to_none)]
_ShortNote = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=300), AfterValidator(_no_control_chars)
]
OptionalShortNote = Annotated[_ShortNote | None, BeforeValidator(_blank_to_none)]


@cache
def _time_zones() -> frozenset[str]:
    return frozenset(available_timezones())


def _time_zone(value: str) -> str:
    if value not in _time_zones():
        raise ValueError("must be an IANA time zone such as Europe/Moscow")
    return value


TimeZoneName = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=64), AfterValidator(_time_zone)
]
