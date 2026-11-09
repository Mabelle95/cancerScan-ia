from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog, User


def audit(
    db: Session,
    user: User | None,
    action: str,
    entity: str,
    entity_id: object = None,
    details: dict | None = None,
    request: Request | None = None,
) -> None:
    """Ajoute une entrée au journal d'activité ; le commit est fait par l'appelant."""
    db.add(
        AuditLog(
            user_id=user.id if user else None,
            action=action,
            entity=entity,
            entity_id=str(entity_id) if entity_id is not None else None,
            details=details or {},
            ip_address=request.client.host if request and request.client else None,
        )
    )
