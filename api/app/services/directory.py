"""Annuaire d'orientation : trouver les structures spécialisées les plus proches de la patiente.

Le point de départ est l'établissement où la patiente a été dépistée (ses coordonnées GPS). La distance
est calculée à vol d'oiseau : la distance par la route est plus longue, elle sert à classer, pas à
estimer un temps de trajet.

⚠️ Les services déclarés par chaque établissement doivent être vérifiés et tenus à jour par l'administrateur :
une structure qui n'a plus de mammographe ou de gynécologue ne doit plus être proposée.
"""

from math import asin, cos, radians, sin, sqrt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Facility, Pathology, RiskLevel

# Libellés courts : affichés tels quels sur le web et le mobile (seule source, pas de copie côté clients)
SERVICES: dict[str, str] = {
    "senologie": "Sénologie",
    "gynecologie": "Gynécologie",
    "oncologie": "Oncologie",
    "chirurgie": "Chirurgie",
    "mammographie": "Mammographie",
    "echographie": "Échographie",
    "colposcopie": "Colposcopie",
    "anatomopathologie": "Biopsie / anapath",
}

# Une structure est proposée si elle offre au moins une de ces consultations spécialisées
SPECIALIST_SERVICES: dict[Pathology, set[str]] = {
    Pathology.SEIN: {"senologie", "gynecologie", "oncologie"},
    Pathology.COL: {"gynecologie", "colposcopie", "oncologie"},
    Pathology.OVAIRE: {"gynecologie", "oncologie"},
    Pathology.ENDOMETRE: {"gynecologie", "oncologie"},
}

# Examens utiles au bilan : à distance égale, la structure qui peut les faire sur place passe devant
USEFUL_EXAMS: dict[Pathology, set[str]] = {
    Pathology.SEIN: {"mammographie", "echographie", "anatomopathologie"},
    Pathology.COL: {"colposcopie", "anatomopathologie"},
    Pathology.OVAIRE: {"echographie", "anatomopathologie"},
    Pathology.ENDOMETRE: {"echographie", "anatomopathologie"},
}

# Niveaux de risque pour lesquels une structure spécialisée est proposée automatiquement
REFERRAL_LEVELS = {RiskLevel.MOYEN, RiskLevel.ELEVE}
MAX_SUGGESTIONS = 3


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance à vol d'oiseau (formule de haversine)."""
    p1, p2 = radians(lat1), radians(lat2)
    a = sin((p2 - p1) / 2) ** 2 + cos(p1) * cos(p2) * sin(radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(a))


def _located(f: Facility | None) -> bool:
    return f is not None and f.latitude is not None and f.longitude is not None


def nearest_specialists(db: Session, pathology: Pathology, origin: Facility | None,
                        limit: int = MAX_SUGGESTIONS) -> list[dict]:
    """Structures proposant une consultation spécialisée pour [pathology], de la plus proche à la plus éloignée.

    Sans coordonnées pour l'établissement de départ, les structures de la même région passent en premier.
    """
    wanted = SPECIALIST_SERVICES.get(pathology, set())
    exams = USEFUL_EXAMS.get(pathology, set())
    candidates = [
        f for f in db.scalars(select(Facility).where(Facility.is_active.is_(True)))
        if wanted & set(f.services or [])
    ]

    def km(f: Facility) -> float | None:
        if _located(origin) and _located(f):
            return distance_km(origin.latitude, origin.longitude, f.latitude, f.longitude)
        return None

    def rank(f: Facility):
        d = km(f)
        same_region = origin is not None and f.region == origin.region
        return (
            d is None,                                   # les structures situées d'abord
            d if d is not None else (0 if same_region else 1),
            -len(exams & set(f.services or [])),         # puis celles qui font le bilan sur place
            f.name,
        )

    out = []
    for f in sorted(candidates, key=rank)[:limit]:
        d = km(f)
        out.append({
            "facility_id": f.id,
            "name": f.name,
            "level": f.level,
            "region": f.region,
            "district": f.district,
            "address": f.address,
            "phone": f.phone,
            "latitude": f.latitude,
            "longitude": f.longitude,
            "distance_km": round(d, 1) if d is not None else None,
            "services": [s for s in SERVICES if s in (f.services or [])],
            "service_labels": [label for s, label in SERVICES.items() if s in (f.services or [])],
            "same_facility": origin is not None and f.id == origin.id,
        })
    return out
