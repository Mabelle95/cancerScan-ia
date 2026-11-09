"""Synchronisation des saisies réalisées hors connexion sur le mobile.

Chaque élément porte un `client_uuid` généré sur l'appareil : renvoyer le même lot est sans effet (idempotence).
Les éléments sont traités un par un pour qu'une erreur n'empêche pas la synchronisation des autres.
"""

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.permissions import Perm
from app.deps import DbSession, require
from app.models import Patient, Screening
from app.schemas import SyncIn, SyncItemResult, SyncOut
from app.services.access import get_accessible_patient
from app.services.records import create_patient, create_screening

router = APIRouter(prefix="/sync", tags=["Synchronisation hors ligne"])


def _sync_screening(db, user, patient, item) -> SyncItemResult:
    existing = db.scalar(select(Screening).where(Screening.client_uuid == item.client_uuid))
    if existing:
        return SyncItemResult(client_uuid=item.client_uuid, server_id=existing.id, status="already_synced")
    screening, _ = create_screening(db, user, patient, item)
    return SyncItemResult(client_uuid=item.client_uuid, server_id=screening.id, status="created")


def _already(db, model, client_uuid) -> SyncItemResult | None:
    """Envoi concurrent du même élément (ex. deux synchronisations simultanées) : l'autre requête l'a déjà créé."""
    found = db.scalar(select(model).where(model.client_uuid == client_uuid))
    return SyncItemResult(client_uuid=client_uuid, server_id=found.id, status="already_synced") if found else None


@router.post("", response_model=SyncOut)
def sync(body: SyncIn, db: DbSession, user=require(Perm.SCREENINGS_WRITE)):
    patients_out: list[SyncItemResult] = []
    screenings_out: list[SyncItemResult] = []

    for item in body.patients:
        try:
            with db.begin_nested():
                patient = db.scalar(select(Patient).where(Patient.client_uuid == item.client_uuid))
                if patient:
                    patients_out.append(SyncItemResult(client_uuid=item.client_uuid, server_id=patient.id, status="already_synced"))
                else:
                    patient = create_patient(db, user, item)
                    patients_out.append(SyncItemResult(client_uuid=item.client_uuid, server_id=patient.id, status="created"))
                for s in item.screenings:
                    screenings_out.append(_sync_screening(db, user, patient, s))
        except IntegrityError:
            patients_out.append(_already(db, Patient, item.client_uuid)
                                or SyncItemResult(client_uuid=item.client_uuid, status="error", detail="Conflit d'enregistrement"))
        except (HTTPException, ValueError, ValidationError) as exc:
            patients_out.append(SyncItemResult(client_uuid=item.client_uuid, status="error", detail=_detail(exc)))

    for item in body.screenings:
        try:
            with db.begin_nested():
                patient = get_accessible_patient(db, user, item.patient_id)
                screenings_out.append(_sync_screening(db, user, patient, item))
        except IntegrityError:
            screenings_out.append(_already(db, Screening, item.client_uuid)
                                  or SyncItemResult(client_uuid=item.client_uuid, status="error", detail="Conflit d'enregistrement"))
        except (HTTPException, ValueError, ValidationError) as exc:
            screenings_out.append(SyncItemResult(client_uuid=item.client_uuid, status="error", detail=_detail(exc)))

    db.commit()
    return SyncOut(patients=patients_out, screenings=screenings_out)


def _detail(exc: Exception) -> str:
    return exc.detail if isinstance(exc, HTTPException) else str(exc)
