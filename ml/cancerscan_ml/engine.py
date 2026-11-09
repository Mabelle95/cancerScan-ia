"""Moteur d'inférence CancerScan (service interne appelé uniquement par l'API).

    uvicorn cancerscan_ml.engine:app --port 8001
"""

import json
import logging
import logging.handlers
import os
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from cancerscan_ml import registry
from cancerscan_ml.features import feature_specs, form_version
from cancerscan_ml.promote import list_models

log = logging.getLogger("cancerscan.engine")


class _JsonFormatter(logging.Formatter):
    """Même format que l'API : une ligne JSON, avec l'identifiant de requête transmis par l'API."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {"time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
                 "level": record.levelname, "logger": record.name, "message": record.getMessage(), "service": "engine"}
        for key in ("request_id", "method", "path", "status", "duration_ms", "pathology", "model_version"):
            if getattr(record, key, None) is not None:
                entry[key] = getattr(record, key)
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def _setup_logging() -> None:
    root = logging.getLogger()
    if getattr(root, "_cancerscan_configured", False):
        return
    root.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    log_dir = os.environ.get("LOG_DIR")
    if log_dir:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        handlers.append(logging.handlers.RotatingFileHandler(Path(log_dir) / "engine.log", maxBytes=10 * 1024 * 1024,
                                                             backupCount=10, encoding="utf-8"))
    for h in handlers:
        h.setFormatter(_JsonFormatter())
        root.addHandler(h)
    logging.getLogger("uvicorn.access").disabled = True
    root._cancerscan_configured = True  # type: ignore[attr-defined]


_setup_logging()
PATHOLOGIES = ("sein", "col", "ovaire", "endometre")

API_KEY = os.environ.get("ENGINE_API_KEY", "change-me")
ALLOW_UNVALIDATED = os.environ.get("ENGINE_ALLOW_UNVALIDATED", "false").lower() == "true"

_models: dict[str, registry.LoadedModel] = {}


def check_key(x_api_key: str = Header(default="")):
    if x_api_key != API_KEY:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Clé d'API invalide")


def reload_models() -> dict[str, str]:
    _models.clear()
    for p in PATHOLOGIES:
        try:
            model = registry.load(p)
        except Exception:  # un artefact illisible ne doit pas bloquer les autres pathologies
            log.exception("Chargement impossible du modèle %s", p)
            continue
        if model is not None:
            _models[p] = model
    return {p: m.metadata["version"] for p, m in _models.items()}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    loaded = reload_models()
    log.info("Modèles chargés : %s (non validés autorisés : %s)", loaded, ALLOW_UNVALIDATED)
    yield


app = FastAPI(title="CancerScan — moteur IA", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def request_log(request: Request, call_next):
    """Journal d'accès (sans corps : les variables cliniques ne sont jamais journalisées)."""
    rid = request.headers.get("x-request-id", "")[:64]
    rid = rid if rid.replace("-", "").isalnum() and rid else uuid.uuid4().hex[:16]
    request.state.request_id = rid
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    log.info("requete", extra={"request_id": rid, "method": request.method, "path": request.url.path,
                               "status": response.status_code, "duration_ms": round((time.perf_counter() - start) * 1000, 1)})
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    rid = getattr(request.state, "request_id", None)
    log.error("Erreur non gérée : %s", type(exc).__name__, exc_info=exc, extra={"request_id": rid})
    return JSONResponse({"detail": f"Erreur interne du moteur IA (référence {rid})", "request_id": rid,
                         "error": type(exc).__name__, "trace": "".join(traceback.format_exception_only(type(exc), exc))[:500]},
                        status_code=500)


class PredictIn(BaseModel):
    pathology: str
    features: dict[str, Any]


@app.get("/health")
def health():
    return {"status": "ok", "models": {p: m.metadata["version"] for p, m in _models.items()}, "allow_unvalidated": ALLOW_UNVALIDATED}


@app.get("/models", dependencies=[Depends(check_key)])
def models():
    return list_models()


@app.post("/reload", dependencies=[Depends(check_key)])
def reload():
    return reload_models()


@app.post("/predict", dependencies=[Depends(check_key)])
def predict(body: PredictIn):
    model = _models.get(body.pathology)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Aucun modèle déployé pour « {body.pathology} »")
    meta = model.metadata
    if not meta.get("validated") and not ALLOW_UNVALIDATED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Le modèle déployé n'est pas validé cliniquement : analyse refusée")
    current = [s.name for s in feature_specs(body.pathology)]
    if set(meta["features"]) != set(current):  # le pipeline sélectionne les colonnes par nom : l'ordre est sans effet
        # Les variables du modèle ont changé depuis l'entraînement (ajout, retrait, renommage) : il faut réentraîner.
        # Ajouter au formulaire des champs non utilisés par le modèle (« ml » absent) reste compatible.
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Variables du modèle (formulaire v{meta['form_version']}) différentes de celles du formulaire "
                            f"actuel v{form_version(body.pathology)} : réentraînement nécessaire")
    unknown = set(body.features) - set(current)
    if unknown:
        raise HTTPException(422, f"Variables inattendues : {sorted(unknown)}")
    result = registry.predict(model, body.features)
    warnings = []
    if not meta.get("validated"):
        warnings.append("Modèle NON validé cliniquement — résultat à usage de développement uniquement.")
    if meta.get("data_source") == "synthetique":
        warnings.append("Modèle entraîné sur des données synthétiques.")
    result["warnings"] = warnings
    return result
