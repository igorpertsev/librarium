from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import Field, StringConstraints

from app.schemas.common import ApiModel, RequestModel

State = Annotated[str, StringConstraints(min_length=1, max_length=2000)]


class PasskeyOptions(ApiModel):
    options: dict[str, Any] = Field(
        description="PublicKeyCredentialCreationOptions / RequestOptions as JSON for the browser"
    )
    state: str = Field(description="Send it back with the browser's answer (5 minutes)")


class PasskeyOptionsRequest(RequestModel):
    password: Annotated[str, StringConstraints(min_length=1, max_length=200)]


class PasskeyRegister(RequestModel):
    state: State
    credential: dict[str, Any] = Field(description="navigator.credentials.create() as JSON")
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class PasskeySignIn(RequestModel):
    state: State
    credential: dict[str, Any] = Field(description="navigator.credentials.get() as JSON")


class PasskeyRead(ApiModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    last_used_at: datetime | None
