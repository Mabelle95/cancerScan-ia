"""Création des dossiers et des dépistages (partagée entre les routes classiques et la synchronisation hors ligne)."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import lookup_hash
from app.models import Patient, Screening, ScreeningStatus, User, utcnow
from app.schemas import PatientIn, ScreeningIn
from app.services.access import scope_patients
from app.services.analysis import run_analysis
from app.services.audit import audit
from app.services.forms import FormCheck, check_form, get_form


def _new_code(user: User) -> str:
    return f"CS-{user.facility.code}-{uuid.uuid4().hex[:8].upper()}"


def possible_duplicates(db: Session, user: User, body: PatientIn, exclude: uuid.UUID | None = None) -> list[Patient]:
    """Doublons probables parmi les dossiers accessibles : même téléphone, ou même nom et même année de naissance."""
    candidates: dict[uuid.UUID, Patient] = {}
    if body.phone:
        for p in db.scalars(scope_patients(select(Patient).where(Patient.phone_lookup == lookup_hash(body.phone)), user)):
            candidates[p.id] = p
    year = body.birth_date.year if body.birth_date else body.birth_year_estimated
    if body.full_name and year:
        # Les noms étant chiffrés, la comparaison se fait après déchiffrement sur un sous-ensemble filtré.
        q = scope_patients(select(Patient).where(Patient.region == body.region), user).limit(5000)
        target = _norm(body.full_name)
        for p in db.scalars(q):
            p_year = p.birth_date.year if p.birth_date else p.birth_year_estimated
            if p.full_name and _norm(p.full_name) == target and p_year and abs(p_year - year) <= 1:
                candidates[p.id] = p
    candidates.pop(exclude, None)
    return list(candidates.values())


def _norm(name: str) -> str:
    return " ".join(sorted(name.lower().split()))


def create_patient(db: Session, user: User, body: PatientIn) -> Patient:
    if user.facility_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Votre compte n'est rattaché à aucun établissement")
    patient = Patient(
        code=_new_code(user),
        facility_id=user.facility_id,
        created_by_id=user.id,
        phone_lookup=lookup_hash(body.phone) if body.phone else None,
        consent_date=body.consent_date or utcnow().date(),
        **body.model_dump(exclude={"consent_date", "screenings"}),
    )
    db.add(patient)
    db.flush()
    audit(db, user, "create", "patient", patient.id)
    return patient


def create_screening(db: Session, user: User, patient: Patient, body: ScreeningIn) -> tuple[Screening, FormCheck]:
    form = get_form(body.pathology)
    screening = Screening(
        patient=patient,
        pathology=body.pathology,
        form_version=form["version"],
        data=body.data,
        facility_id=user.facility_id or patient.facility_id,
        created_by_id=user.id,
        client_uuid=body.client_uuid,
    )
    db.add(screening)
    db.flush()
    audit(db, user, "create", "screening", screening.id, {"pathology": body.pathology.value})
    check = check_form(body.pathology, body.data)
    screening.alerts = check.alerts
    if body.submit:
        submit_screening(db, user, screening, check)
    return screening, check


def submit_screening(db: Session, user: User, screening: Screening, check: FormCheck | None = None) -> FormCheck:
    """Soumet le dépistage à l'analyse si les données sont complètes et cohérentes ; sinon il reste en brouillon."""
    check = check or check_form(screening.pathology, screening.data)
    screening.alerts = check.alerts
    if not check.is_complete:
        return check
    screening.status = ScreeningStatus.SUBMITTED
    screening.submitted_at = screening.submitted_at or utcnow()
    run_analysis(db, screening, user)
    return check
