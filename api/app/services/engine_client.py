"""Client HTTP du moteur IA."""

from typing import Any

import httpx

from app.core.config import get_settings
from app.core.observability import request_id_var


class EngineUnavailable(Exception):
    """Le moteur ne répond pas ou aucun modèle utilisable n'est déployé : l'analyse est différée."""

    def __init__(self, message: str, server_error: dict | None = None):
        super().__init__(message)
        # Renseigné quand le moteur a répondu par une erreur 5xx : à enregistrer comme erreur technique
        self.server_error = server_error


def predict(pathology: str, features: dict[str, Any]) -> dict:
    settings = get_settings()
    try:
        response = httpx.post(
            f"{settings.engine_url}/predict",
            json={"pathology": pathology, "features": features},
            # Même identifiant de requête dans les logs de l'API et du moteur IA
            headers={"X-API-Key": settings.engine_api_key, "X-Request-ID": request_id_var.get() or ""},
            timeout=settings.engine_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise EngineUnavailable(f"Moteur IA injoignable : {exc}") from exc
    if response.status_code in (404, 409, 503):
        raise EngineUnavailable(response.json().get("detail", "Aucun modèle disponible"))
    if response.status_code >= 500:
        # Panne du moteur : l'analyse est différée (le dépistage reste « soumis ») au lieu de faire échouer la saisie.
        rid = request_id_var.get()
        raise EngineUnavailable(
            f"Erreur du moteur IA (référence {rid})",
            server_error={"message": f"Moteur IA : erreur HTTP {response.status_code}", "request_id": rid,
                          "body": response.text[:1000]},
        )
    response.raise_for_status()
    return response.json()


def list_models() -> list[dict]:
    settings = get_settings()
    try:
        response = httpx.get(
            f"{settings.engine_url}/models",
            headers={"X-API-Key": settings.engine_api_key},
            timeout=settings.engine_timeout_seconds,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise EngineUnavailable(f"Moteur IA injoignable : {exc}") from exc
    return response.json()
