import uuid

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import select

from app.core.permissions import Perm
from app.core.security import lookup_hash
from app.deps import DbSession, require
from app.models import ExamResult, Patient, Screening
from app.schemas import (
    ExamIn, ExamOut, PatientCreated, PatientIn, PatientOut, PatientSummary, PatientUpdate, ScreeningIn, ScreeningOut,
    SubmitResult,
)
from app.services.access import get_accessible_patient, scope_patients
from app.services.audit import audit
from app.services.records import create_patient, create_screening, possible_duplicates

router = APIRouter(prefix="/patients", tags=["Patientes"])


@router.get("", response_model=list[PatientSummary])
def search_patients(
    db: DbSession,
    request: Request,
    user=require(Perm.PATIENTS_READ),
    q: str | None = Query(None, description="Code patiente, téléphone ou nom"),
    limit: int = Query(50, le=200),
):
    query = scope_patients(select(Patient), user).order_by(Patient.created_at.desc())
    if not q:
        results = db.scalars(query.limit(limit)).all()
    elif q.upper().startswith("CS-"):
        results = db.scalars(query.where(Patient.code.startswith(q.upper())).limit(limit)).all()
    elif sum(c.isdigit() for c in q) >= 8:
        results = db.scalars(query.where(Patient.phone_lookup == lookup_hash(q)).limit(limit)).all()
    else:
        # Recherche par nom : les noms sont chiffrés, le filtrage se fait après déchiffrement.
        needle = q.lower()
        results = [p for p in db.scalars(query.limit(5000)) if p.full_name and needle in p.full_name.lower()][:limit]
    audit(db, user, "search", "patient", details={"results": len(results)}, request=request)
    db.commit()
    return results


@router.post("", response_model=PatientCreated, status_code=201)
def register_patient(body: PatientIn, db: DbSession, request: Request, user=require(Perm.PATIENTS_WRITE)):
    if body.client_uuid:
        existing = db.scalar(select(Patient).where(Patient.client_uuid == body.client_uuid))
        if existing:
            return PatientCreated(patient=PatientOut.model_validate(existing))
    duplicates = possible_duplicates(db, user, body)
    patient = create_patient(db, user, body)
    db.commit()
    return PatientCreated(patient=PatientOut.model_validate(patient), possible_duplicates=duplicates)


@router.get("/{patient_id}", response_model=PatientOut)
def get_patient(patient_id: uuid.UUID, db: DbSession, request: Request, user=require(Perm.PATIENTS_READ)):
    patient = get_accessible_patient(db, user, patient_id)
    audit(db, user, "read", "patient", patient.id, request=request)
    db.commit()
    return patient


@router.patch("/{patient_id}", response_model=PatientOut)
def update_patient(patient_id: uuid.UUID, body: PatientUpdate, db: DbSession, request: Request, user=require(Perm.PATIENTS_WRITE)):
    patient = get_accessible_patient(db, user, patient_id)
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(patient, k, v)
    if "phone" in changes:
        patient.phone_lookup = lookup_hash(changes["phone"]) if changes["phone"] else None
    audit(db, user, "update", "patient", patient.id, {"fields": sorted(changes)}, request)
    db.commit()
    return patient


@router.get("/{patient_id}/screenings", response_model=list[ScreeningOut])
def patient_screenings(patient_id: uuid.UUID, db: DbSession, user=require(Perm.SCREENINGS_READ)):
    patient = get_accessible_patient(db, user, patient_id)
    return patient.screenings


@router.post("/{patient_id}/screenings", response_model=SubmitResult, status_code=201)
def new_screening(patient_id: uuid.UUID, body: ScreeningIn, db: DbSession, user=require(Perm.SCREENINGS_WRITE)):
    patient = get_accessible_patient(db, user, patient_id)
    if body.client_uuid:
        existing = db.scalar(select(Screening).where(Screening.client_uuid == body.client_uuid))
        if existing:
            return SubmitResult(screening=ScreeningOut.model_validate(existing))
    screening, check = create_screening(db, user, patient, body)
    db.commit()
    return SubmitResult(
        screening=ScreeningOut.model_validate(screening),
        missing_required=check.missing_required,
        errors=check.errors,
        ai_pending=body.submit and check.is_complete and not screening.assessments,
    )


@router.get("/{patient_id}/exams", response_model=list[ExamOut])
def patient_exams(patient_id: uuid.UUID, db: DbSession, user=require(Perm.PATIENTS_READ)):
    patient = get_accessible_patient(db, user, patient_id)
    return db.scalars(select(ExamResult).where(ExamResult.patient_id == patient.id).order_by(ExamResult.created_at.desc())).all()


@router.post("/{patient_id}/exams", response_model=ExamOut, status_code=201)
def add_exam(patient_id: uuid.UUID, body: ExamIn, db: DbSession, request: Request, user=require(Perm.EXAMS_WRITE)):
    patient = get_accessible_patient(db, user, patient_id)
    if body.screening_id:
        screening = db.get(Screening, body.screening_id)
        if screening is None or screening.patient_id != patient.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Dépistage non rattaché à cette patiente")
    exam = ExamResult(patient_id=patient.id, recorded_by_id=user.id, **body.model_dump())
    db.add(exam)
    db.flush()
    audit(db, user, "create", "exam", exam.id, {"type": body.exam_type.value}, request)
    db.commit()
    return exam
