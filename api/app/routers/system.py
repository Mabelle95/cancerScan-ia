"""Supervision : remontée des erreurs des applications, état du système, liste des erreurs."""

import time
from collections import defaultdict, deque
from datetime import timedelta
from typing import Annotated, Literal

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.core.observability import metrics
from app.core.permissions import Perm
from app.core.security import decode_access_token
from app.deps import DbSession, bearer, require
from app.models import ErrorEvent, Screening, ScreeningStatus, utcnow
from app.services.errors import record_error

router = APIRouter(tags=["Supervision"])

# Limite simple par adresse IP pour la remontée d'erreurs (évite qu'un client défaillant inonde la base)
_RATE: dict[str, deque] = defaultdict(lambda: deque(maxlen=30))
_RATE_WINDOW = 60.0


class ClientError(BaseModel):
    source: Literal["web", "mobile"]
    message: str = Field(max_length=1000)
    stack: str | None = Field(default=None, max_length=4000)
    app_version: str | None = Field(default=None, max_length=40)
    platform: str | None = Field(default=None, max_length=60)
    screen: str | None = Field(default=None, max_length=120)
    request_id: str | None = Field(default=None, max_length=64)


class ErrorOut(BaseModel):
    id: int
    source: str
    level: str
    message: str
    request_id: str | None
    path: str | None
    user_id: int | None
    details: dict
    resolved: bool
    created_at: str


def _user_id(credentials: HTTPAuthorizationCredentials | None) -> int | None:
    if credentials is None:
        return None
    try:
        return int(decode_access_token(credentials.credentials)["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


@router.post("/client-errors", status_code=202)
def report_client_error(
    body: ClientError,
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    """Erreur survenue dans le site Web ou l'application mobile. Ne doit contenir aucune donnée de patiente."""
    ip = request.client.host if request.client else "?"
    now = time.monotonic()
    hits = _RATE[ip]
    while hits and now - hits[0] > _RATE_WINDOW:
        hits.popleft()
    if len(hits) >= hits.maxlen:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Trop de rapports d'erreur : réessayez plus tard")
    hits.append(now)
    event_id = record_error(
        body.source, body.message, request_id=body.request_id, path=body.screen, user_id=_user_id(credentials),
        details={k: v for k, v in {"stack": body.stack, "app_version": body.app_version, "platform": body.platform}.items() if v},
    )
    return {"id": event_id}


def _serialize(e: ErrorEvent) -> ErrorOut:
    return ErrorOut(id=e.id, source=e.source, level=e.level, message=e.message, request_id=e.request_id, path=e.path,
                    user_id=e.user_id, details=e.details, resolved=e.resolved, created_at=e.created_at.isoformat())


@router.get("/system/errors", response_model=list[ErrorOut])
def list_errors(
    db: DbSession,
    _=require(Perm.AUDIT_READ),
    source: str | None = None,
    include_resolved: bool = False,
    request_id: str | None = None,
    limit: int = Query(100, le=500),
):
    q = select(ErrorEvent).order_by(ErrorEvent.created_at.desc())
    if source:
        q = q.where(ErrorEvent.source == source)
    if request_id:
        q = q.where(ErrorEvent.request_id == request_id)
    if not include_resolved:
        q = q.where(ErrorEvent.resolved.is_(False))
    return [_serialize(e) for e in db.scalars(q.limit(limit))]


@router.post("/system/errors/{error_id}/resolve", response_model=ErrorOut)
def resolve_error(error_id: int, db: DbSession, _=require(Perm.AUDIT_READ)):
    event = db.get(ErrorEvent, error_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Erreur introuvable")
    event.resolved = True
    db.commit()
    return _serialize(event)


@router.get("/system/status")
def system_status(db: DbSession, _=require(Perm.AUDIT_READ)):
    """État des composants pour l'administrateur."""
    settings = get_settings()
    try:
        db.execute(text("SELECT 1"))
        database = {"status": "ok"}
    except Exception as exc:  # noqa: BLE001
        database = {"status": "erreur", "detail": type(exc).__name__}

    try:
        r = httpx.get(f"{settings.engine_url}/health", timeout=3)
        r.raise_for_status()
        body = r.json()
        engine = {"status": "ok", "models": body.get("models", {}), "allow_unvalidated": body.get("allow_unvalidated")}
    except httpx.HTTPError as exc:
        engine = {"status": "injoignable", "detail": type(exc).__name__}

    since = utcnow() - timedelta(hours=24)
    errors_24h = dict(db.execute(
        select(ErrorEvent.source, func.count()).where(ErrorEvent.created_at >= since).group_by(ErrorEvent.source)
    ).all())
    unresolved = db.scalar(select(func.count()).select_from(ErrorEvent).where(ErrorEvent.resolved.is_(False)))
    pending_ai = db.scalar(select(func.count()).select_from(Screening).where(Screening.status == ScreeningStatus.SUBMITTED))
    overall = "ok" if database["status"] == "ok" and engine["status"] == "ok" else "degrade"
    return {
        "status": overall,
        "version": "0.1.0",
        "api": metrics.snapshot(),
        "database": database,
        "engine": engine,
        "errors_last_24h": errors_24h,
        "unresolved_errors": unresolved,
        "screenings_pending_ai": pending_ai,
        "logs": str(settings.log_dir) if settings.log_dir else "console",
    }
