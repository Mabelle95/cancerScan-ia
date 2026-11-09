"""Gestionnaires d'erreurs globaux : réponses en français, référence de requête, jamais de détail technique."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.observability import short_traceback
from app.services.errors import record_error

log = logging.getLogger("cancerscan.errors")

# Messages de validation Pydantic traduits (les messages métier sont déjà en français)
_FRENCH = {
    "missing": "Champ obligatoire",
    "value_error": None,  # message métier déjà rédigé en français (« Value error, … »)
    "string_too_short": "Texte trop court",
    "string_too_long": "Texte trop long",
    "string_pattern_mismatch": "Format invalide",
    "int_parsing": "Nombre entier attendu",
    "float_parsing": "Nombre attendu",
    "bool_parsing": "Valeur oui / non attendue",
    "date_from_datetime_parsing": "Date invalide (AAAA-MM-JJ)",
    "date_parsing": "Date invalide (AAAA-MM-JJ)",
    "uuid_parsing": "Identifiant invalide",
    "enum": "Valeur non reconnue",
    "literal_error": "Valeur non reconnue",
    "greater_than_equal": "Valeur trop petite",
    "less_than_equal": "Valeur trop grande",
    "json_invalid": "Requête mal formée",
}

_FIELDS = {"email": "Adresse e-mail", "password": "Mot de passe", "new_password": "Nouveau mot de passe",
           "region": "Région", "consent_given": "Consentement", "pathology": "Pathologie"}


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _french(err: dict) -> str:
    field = next((str(p) for p in reversed(err.get("loc", ())) if isinstance(p, str) and p != "body"), None)
    label = _FIELDS.get(field or "", field)
    if err.get("type") == "value_error" and "email" in str(err.get("msg", "")).lower():
        msg = "Adresse e-mail invalide"
    elif err.get("type") == "value_error":
        msg = str(err.get("msg", "")).removeprefix("Value error, ")
    else:
        msg = _FRENCH.get(err.get("type", ""), "Valeur invalide")
    return f"{label} : {msg}" if label and err.get("type") != "value_error" else msg


def install(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        rid = _request_id(request)
        return JSONResponse({"detail": exc.detail, "request_id": rid}, status_code=exc.status_code,
                            headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        errors = [{"loc": list(e.get("loc", ())), "msg": _french(e), "type": e.get("type")} for e in exc.errors()]
        return JSONResponse({"detail": errors, "request_id": _request_id(request)}, status_code=422)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        rid = _request_id(request)
        log.error("Erreur non gérée : %s", type(exc).__name__, exc_info=exc)
        record_error(
            "api", f"{type(exc).__name__}: {exc}"[:1000], request_id=rid, path=request.url.path,
            user_id=getattr(request.state, "user_id", None), details={"traceback": short_traceback(exc)},
        )
        return JSONResponse(
            {"detail": f"Erreur interne du serveur. Communiquez cette référence au support : {rid}", "request_id": rid},
            status_code=500, headers={"X-Request-ID": rid or ""},
        )
