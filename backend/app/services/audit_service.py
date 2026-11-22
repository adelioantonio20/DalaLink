import json
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.mobility import AuditLog, Notification


def record_audit(
    db: Session,
    action: str,
    entity_type: str,
    entity_id: Optional[str | int] = None,
    actor_user_id: Optional[int] = None,
    details: Optional[dict[str, Any]] = None,
) -> AuditLog:
    log = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        details_json=json.dumps(details or {}, ensure_ascii=False, default=str),
    )
    db.add(log)
    return log


def create_notification(
    db: Session,
    user_id: int,
    title: str,
    message: str,
    category: str = "TRIP",
) -> Notification:
    notif = Notification(
        user_id=user_id,
        title=title,
        message=message,
        category=category,
    )
    db.add(notif)
    return notif
