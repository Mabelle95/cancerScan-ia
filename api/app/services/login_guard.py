"""Limite des échecs de connexion par adresse IP (en mémoire, par processus).

Complète le blocage par compte (stocké en base) : empêche d'essayer de nombreux comptes depuis la même machine.
En production derrière un proxy, l'adresse doit venir de l'en-tête X-Forwarded-For fourni par le proxy de confiance ;
avec plusieurs processus, utiliser un stockage partagé (ex. Redis).
"""

import time
from collections import defaultdict, deque

from app.core.config import get_settings

_failures: dict[str, deque[float]] = defaultdict(deque)


def _prune(ip: str, now: float) -> deque[float]:
    window = get_settings().login_ip_window_minutes * 60
    q = _failures[ip]
    while q and now - q[0] > window:
        q.popleft()
    return q


def blocked_for(ip: str) -> int:
    """Secondes restantes de blocage (0 si l'adresse peut tenter une connexion)."""
    settings = get_settings()
    now = time.monotonic()
    q = _prune(ip, now)
    if len(q) < settings.login_ip_max_failures:
        return 0
    return max(1, int(settings.login_ip_window_minutes * 60 - (now - q[0])))


def record_failure(ip: str) -> None:
    q = _prune(ip, time.monotonic())
    q.append(time.monotonic())


def reset(ip: str | None = None) -> None:
    if ip is None:
        _failures.clear()
    else:
        _failures.pop(ip, None)
