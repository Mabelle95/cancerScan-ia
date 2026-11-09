"""Logs structurés, identifiant de requête, métriques et enregistrement des erreurs.

Règle de confidentialité : les logs ne contiennent JAMAIS de corps de requête ni de paramètres de recherche
(ils peuvent contenir un nom ou un téléphone). Seuls le chemin, le code de réponse, la durée, l'identifiant de
l'utilisateur et l'identifiant de requête sont journalisés.
"""

import json
import logging
import logging.handlers
import time
import traceback
import uuid
from collections import deque
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_var: ContextVar[int | None] = ContextVar("user_id", default=None)

STARTED_AT = time.time()
access_log = logging.getLogger("cancerscan.access")
log = logging.getLogger("cancerscan")


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = getattr(record, "request_id", None) or request_id_var.get()
        record.user_id = getattr(record, "user_id", None) or user_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """Une ligne JSON par événement : exploitable par un outil d'analyse de logs."""

    _extra = ("method", "path", "status", "duration_ms", "client_ip", "source")

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
            "user_id": getattr(record, "user_id", None),
        }
        for key in self._extra:
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps({k: v for k, v in entry.items() if v is not None}, ensure_ascii=False)


def setup_logging(log_dir: Path | None, level: str = "INFO", service: str = "api") -> None:
    """Console + fichier tournant (10 Mo × 10) ; idempotent."""
    root = logging.getLogger()
    if getattr(root, "_cancerscan_configured", False):
        return
    root.setLevel(level)
    formatter, ctx = JsonFormatter(), ContextFilter()
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.handlers.RotatingFileHandler(
            log_dir / f"{service}.log", maxBytes=10 * 1024 * 1024, backupCount=10, encoding="utf-8"))
    for h in handlers:
        h.setFormatter(formatter)
        h.addFilter(ctx)
        root.addHandler(h)
    # Ces journaux contiennent l'URL complète avec la chaîne de requête (?q=nom…) : uvicorn.access est remplacé par
    # le nôtre, et les clients HTTP ne journalisent que les avertissements (fuite détectée par les tests).
    logging.getLogger("uvicorn.access").disabled = True
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    root._cancerscan_configured = True  # type: ignore[attr-defined]


class Metrics:
    """Compteurs en mémoire pour la page « État du système » (réinitialisés au redémarrage)."""

    def __init__(self, window: int = 1000):
        self.requests = 0
        self.server_errors = 0
        self.client_errors = 0
        self.durations: deque[float] = deque(maxlen=window)

    def record(self, status: int, duration_ms: float) -> None:
        self.requests += 1
        self.durations.append(duration_ms)
        if status >= 500:
            self.server_errors += 1
        elif status >= 400:
            self.client_errors += 1

    def snapshot(self) -> dict:
        d = sorted(self.durations)
        pct = lambda p: round(d[min(len(d) - 1, int(len(d) * p))], 1) if d else None  # noqa: E731
        return {
            "uptime_seconds": int(time.time() - STARTED_AT),
            "requests": self.requests,
            "server_errors": self.server_errors,
            "client_errors": self.client_errors,
            "latency_ms_p50": pct(0.5),
            "latency_ms_p95": pct(0.95),
        }


metrics = Metrics()


class RequestContextMiddleware:
    """Middleware ASGI : identifiant de requête (repris de X-Request-ID ou généré), durée, journal d'accès."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        incoming = dict(scope.get("headers") or []).get(b"x-request-id", b"").decode()[:64]
        request_id = incoming if incoming.replace("-", "").isalnum() and incoming else uuid.uuid4().hex[:16]
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_var.set(request_id)
        user_token = user_id_var.set(None)
        status_holder = {"status": 500}
        start = time.perf_counter()

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                message.setdefault("headers", []).append((b"x-request-id", request_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = (time.perf_counter() - start) * 1000
            status = status_holder["status"]
            metrics.record(status, duration)
            client = scope.get("client")
            access_log.log(
                logging.WARNING if status >= 500 else logging.INFO,
                "requete",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],  # sans la chaîne de requête, volontairement
                    "status": status,
                    "duration_ms": round(duration, 1),
                    "client_ip": client[0] if client else None,
                    # Posé par l'authentification dans l'état de la requête (partagé entre threads, contrairement au contextvar)
                    "user_id": scope["state"].get("user_id"),
                },
            )
            request_id_var.reset(token)
            user_id_var.reset(user_token)


def short_traceback(exc: BaseException, limit: int = 4000) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-limit:]
