from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.common import ApiModel, Page


class AuditEventRead(ApiModel):
    id: uuid.UUID
    created_at: datetime
    actor_email: str
    action: str = Field(description="Endpoint name, e.g. admin_change_order_status")
    method: str
    path: str
    entity_type: str | None
    entity_id: uuid.UUID | None
    entity_label: str | None = Field(description="Book title, order number or user email")
    details: dict[str, Any]


class AuditPage(Page[AuditEventRead]):
    pass
