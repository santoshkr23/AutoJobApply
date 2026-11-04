"""Append-only audit trail. Never log secrets, passwords or resume content here."""

import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.ratelimit import client_ip
from app.models.base import utcnow
from app.models.misc import AuditLog


def audit(
    db: Session,
    *,
    action: str,
    actor_type: str = "system",
    actor_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: Any = None,
    request: Request | None = None,
    meta: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            ip_address=client_ip(request) if request else None,
            user_agent=(request.headers.get("user-agent", "")[:255] if request else None),
            meta=meta or {},
            created_at=utcnow(),
        )
    )
