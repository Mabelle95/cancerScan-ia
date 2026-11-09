"""Enregistrement des erreurs techniques (table system_errors), sans jamais faire échouer l'appelant."""

import logging

from app.db import SessionLocal
from app.models import ErrorEvent

log = logging.getLogger("cancerscan.errors")

MAX_MESSAGE = 1000


def record_error(source: str, message: str, *, request_id: str | None = None, path: str | None = None,
                 user_id: int | None = None, details: dict | None = None, level: str = "error") -> int | None:
    """Session dédiée : la session de la requête peut être dans un état invalide après une exception."""
    try:
        with SessionLocal() as db:
            event = ErrorEvent(source=source, level=level, message=message[:MAX_MESSAGE], request_id=request_id,
                               path=(path or "")[:300] or None, user_id=user_id, details=details or {})
            db.add(event)
            db.commit()
            return event.id
    except Exception:  # la supervision ne doit jamais provoquer une seconde panne
        log.exception("Impossible d'enregistrer l'erreur en base")
        return None
