"""Données initiales : administrateur et établissements de démonstration.

Usage : `python -m app.seed` (idempotent). Ajouter `--demo` pour créer des comptes de test par rôle
(développement uniquement, mot de passe identique à ADMIN_PASSWORD).
"""

import sys

from sqlalchemy import select

from app.core.config import get_settings
from app.core.permissions import Role
from app.core.security import hash_password
from app.db import SessionLocal
from app.models import Facility, User

# Établissements fictifs pour le développement — à remplacer par la liste officielle des formations sanitaires.
# Coordonnées : centre approximatif de la ville (pour le calcul des distances) ; services : fictifs.
DEMO_FACILITIES = [
    {"code": "LOM01", "name": "Centre de santé démo Lomé", "region": "Maritime", "district": "Golfe", "level": "CMS",
     "latitude": 6.1725, "longitude": 1.2314, "services": []},
    {"code": "LOM-CHU", "name": "CHU démo Lomé (référence)", "region": "Maritime", "district": "Golfe", "level": "CHU",
     "latitude": 6.1319, "longitude": 1.2228, "address": "Lomé (adresse de démonstration)", "phone": "+228 22 00 00 01",
     "services": ["senologie", "gynecologie", "oncologie", "chirurgie", "mammographie", "echographie", "colposcopie",
                  "anatomopathologie"]},
    {"code": "TSE-CHR", "name": "CHR démo Tsévié", "region": "Maritime", "district": "Zio", "level": "CHR",
     "latitude": 6.4261, "longitude": 1.2133, "phone": "+228 22 00 00 02", "services": ["gynecologie", "echographie"]},
    {"code": "ATA-CHR", "name": "CHR démo Atakpamé", "region": "Plateaux", "district": "Ogou", "level": "CHR",
     "latitude": 7.5333, "longitude": 1.1333, "phone": "+228 24 00 00 03", "services": ["gynecologie", "echographie"]},
    {"code": "SOK-CHR", "name": "CHR démo Sokodé", "region": "Centrale", "district": "Tchaoudjo", "level": "CHR",
     "latitude": 8.9833, "longitude": 1.1333, "phone": "+228 25 00 00 04", "services": ["gynecologie", "echographie"]},
    {"code": "KAR01", "name": "Centre de santé démo Kara", "region": "Kara", "district": "Kozah", "level": "CMS",
     "latitude": 9.5600, "longitude": 1.1800, "services": []},
    {"code": "KAR-CHU", "name": "CHU démo Kara (référence)", "region": "Kara", "district": "Kozah", "level": "CHU",
     "latitude": 9.5511, "longitude": 1.1861, "phone": "+228 26 00 00 05",
     "services": ["senologie", "gynecologie", "chirurgie", "mammographie", "echographie", "anatomopathologie"]},
    {"code": "DAP-CHR", "name": "CHR démo Dapaong", "region": "Savanes", "district": "Tône", "level": "CHR",
     "latitude": 10.8622, "longitude": 0.2076, "phone": "+228 27 00 00 06", "services": ["gynecologie", "echographie"]},
]

DEMO_USERS = [
    ("agent@cancerscan.tg", "Agent de santé démo", Role.AGENT, "LOM01"),
    ("medecin@cancerscan.tg", "Médecin démo", Role.MEDECIN, "LOM01"),
    ("specialiste@cancerscan.tg", "Spécialiste démo", Role.SPECIALISTE, "LOM-CHU"),
    ("responsable@cancerscan.tg", "Responsable sanitaire démo", Role.RESPONSABLE, None),
]


def seed(demo: bool = False) -> None:
    settings = get_settings()
    with SessionLocal() as db:
        facilities = {f.code: f for f in db.scalars(select(Facility))}
        for data in DEMO_FACILITIES:
            existing = facilities.get(data["code"])
            if existing is None:
                facilities[data["code"]] = Facility(**data)
                db.add(facilities[data["code"]])
            else:
                # Complète l'annuaire d'une base créée avant l'ajout des coordonnées (sans écraser une saisie)
                for key in ("latitude", "longitude", "address", "phone", "services"):
                    if data.get(key) and not getattr(existing, key):
                        setattr(existing, key, data[key])
        db.flush()

        accounts = [(settings.admin_email, "Administrateur", Role.ADMIN, None)]
        if demo:
            accounts += DEMO_USERS
        for email, name, role, fcode in accounts:
            if db.scalar(select(User).where(User.email == email)) is None:
                db.add(User(
                    email=email, full_name=name, role=role,
                    facility_id=facilities[fcode].id if fcode else None,
                    hashed_password=hash_password(settings.admin_password),
                ))
                print(f"Compte créé : {email} ({role.value})")
        db.commit()


if __name__ == "__main__":
    seed(demo="--demo" in sys.argv or get_settings().environment == "development")
