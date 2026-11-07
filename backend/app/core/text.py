"""Text that PostgreSQL can store: no NUL characters and no lone UTF-16 surrogates.

JSON allows both ("\\u0000", "\\ud800"), but PostgreSQL rejects NUL in text and a lone surrogate
cannot be encoded as UTF-8, so such input used to end in a 500. Request bodies and parameters are
checked up front and answered with a 422 instead.
"""

from __future__ import annotations

import re

_UNSTORABLE = re.compile("[\x00\ud800-\udfff]")
MESSAGE = "Text must not contain NUL characters or broken Unicode"


def unstorable(value: object) -> bool:
    """True if ``value`` (or any string inside it) contains characters the database refuses."""
    if isinstance(value, str):
        return _UNSTORABLE.search(value) is not None
    if isinstance(value, dict):
        return any(unstorable(k) or unstorable(v) for k, v in value.items())
    if isinstance(value, list | tuple):
        return any(unstorable(item) for item in value)
    return False
