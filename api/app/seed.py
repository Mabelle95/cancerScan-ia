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
DEMO_FACILITIES = [
    {"code": "LOM01", "name": "Centre de santé démo Lomé", "region": "Maritime", "district": "Golfe", "level": "CMS"},
    {"code": "LOM-CHU", "name": "CHU démo Lomé (référence)", "region": "Maritime", "district": "Golfe", "level": "CHU"},
    {"code": "KAR01", "name": "Centre de santé démo Kara", "region": "Kara", "district": "Kozah", "level": "CMS"},
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
            if data["code"] not in facilities:
                facilities[data["code"]] = Facility(**data)
                db.add(facilities[data["code"]])
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
