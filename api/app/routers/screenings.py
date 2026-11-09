import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.core.permissions import Perm
from app.deps import CurrentUser, DbSession, require
from app.models import Patient, Screening, ScreeningStatus
from app.schemas import ScreeningOut, ScreeningUpdate, SubmitResult
from app.services.access import scope_patients
from app.services.analysis import run_analysis
from app.services.audit import audit
from app.services.forms import check_after_result, check_form, load_forms
from app.services.records import submit_screening

router = APIRouter(tags=["Dépistages"])


@router.get("/forms")
def list_forms(_: CurrentUser):
    """Formulaires de dépistage (mis en cache par le mobile pour le mode hors ligne)."""
    return list(load_forms().values())


def _get_screening(db, user, screening_id: uuid.UUID) -> Screening:
    accessible = scope_patients(select(Patient.id), user)
    screening = db.scalar(select(Screening).where(Screening.id == screening_id, Screening.patient_id.in_(accessible)))
    if screening is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dépistage introuvable ou non accessible")
    return screening


@router.get("/screenings/{screening_id}", response_model=ScreeningOut)
def get_screening(screening_id: uuid.UUID, db: DbSession, request: Request, user=require(Perm.SCREENINGS_READ)):
    screening = _get_screening(db, user, screening_id)
    audit(db, user, "read", "screening", screening.id, request=request)
    db.commit()
    return screening


@router.put("/screenings/{screening_id}", response_model=SubmitResult)
def update_screening(screening_id: uuid.UUID, body: ScreeningUpdate, db: DbSession, request: Request, user=require(Perm.SCREENINGS_WRITE)):
    screening = _get_screening(db, user, screening_id)
    if screening.status == ScreeningStatus.VALIDATED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Dépistage déjà validé : créer un nouveau dépistage pour une nouvelle évaluation")
    screening.data = body.data
    check = check_form(screening.pathology, body.data)
    screening.alerts = check.alerts
    audit(db, user, "update", "screening", screening.id, request=request)
    # Un dépistage déjà analysé est ré-analysé avec les données corrigées (l'historique des analyses est conservé).
    if screening.status != ScreeningStatus.DRAFT and check.is_complete:
        run_analysis(db, screening, user)
    db.commit()
    return SubmitResult(screening=ScreeningOut.model_validate(screening), missing_required=check.missing_required, errors=check.errors)


@router.post("/screenings/{screening_id}/submit", response_model=SubmitResult)
def submit(screening_id: uuid.UUID, db: DbSession, user=require(Perm.SCREENINGS_WRITE)):
    screening = _get_screening(db, user, screening_id)
    if screening.status == ScreeningStatus.VALIDATED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Dépistage déjà validé")
    check = submit_screening(db, user, screening)
    db.commit()
    return SubmitResult(
        screening=ScreeningOut.model_validate(screening),
        missing_required=check.missing_required,
        errors=check.errors,
        ai_pending=check.is_complete and screening.status == ScreeningStatus.SUBMITTED,
    )


@router.patch("/screenings/{screening_id}/agent-notes", response_model=ScreeningOut)
def save_agent_notes(screening_id: uuid.UUID, body: dict[str, Any], db: DbSession, request: Request, user=require(Perm.SCREENINGS_WRITE)):
    """Appréciation de l'agent donnée APRÈS le résultat de l'IA : enregistrée sans relancer l'analyse."""
    screening = _get_screening(db, user, screening_id)
    if not screening.assessments:
        raise HTTPException(status.HTTP_409_CONFLICT, "Le résultat de l'analyse IA doit être disponible avant votre appréciation")
    cleaned, errors = check_after_result(screening.pathology, body)
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "; ".join(f"{k} : {v}" for k, v in errors.items()))
    data = dict(screening.data)
    for key, value in cleaned.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    screening.data = data  # nouvelle valeur : SQLAlchemy détecte la modification du JSON
    audit(db, user, "agent_notes", "screening", screening.id, {"fields": sorted(cleaned)}, request)
    db.commit()
    return screening


@router.post("/screenings/process-pending")
def process_pending(db: DbSession, user=require(Perm.SCREENINGS_WRITE)):
    """Relance l'analyse des dépistages soumis dont le calcul IA a été différé (moteur indisponible, synchronisation)."""
    accessible = scope_patients(select(Patient.id), user)
    pending = db.scalars(
        select(Screening).where(Screening.status == ScreeningStatus.SUBMITTED, Screening.patient_id.in_(accessible)).limit(200)
    ).all()
    analysed = sum(run_analysis(db, s, user) is not None for s in pending)
    db.commit()
    return {"pending": len(pending), "analysed": analysed}
