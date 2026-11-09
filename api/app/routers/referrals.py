"""Orientation : validation par un professionnel de santé et suivi des références."""

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import case, select

from app.core.permissions import Perm
from app.deps import DbSession, require
from app.models import Facility, Patient, Referral, ReferralStatus, RiskLevel, Screening, ScreeningStatus, utcnow
from app.schemas import ReferralDecision, ReferralListItem, ReferralOut, ReferralStatusUpdate
from app.services.access import scope_patients
from app.services.audit import audit

router = APIRouter(prefix="/referrals", tags=["Orientations et suivi"])

# Délai après le rendez-vous au-delà duquel une référence non réalisée est signalée « perdue de vue » (à valider)
LOST_TO_FOLLOW_UP_DAYS = 30

_SEVERITY = case(
    {RiskLevel.ELEVE.value: 0, RiskLevel.MOYEN.value: 1, RiskLevel.FAIBLE.value: 2}, value=Referral.proposed_level, else_=3
)


def _get(db, user, referral_id: int) -> Referral:
    accessible = scope_patients(select(Patient.id), user)
    referral = db.scalar(select(Referral).where(Referral.id == referral_id, Referral.patient_id.in_(accessible)))
    if referral is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Orientation introuvable ou non accessible")
    return referral


def _item(r: Referral, patient: Patient, screening: Screening) -> ReferralListItem:
    return ReferralListItem.model_validate(
        {**ReferralOut.model_validate(r).model_dump(), "patient_code": patient.code, "pathology": screening.pathology}
    )


@router.get("", response_model=list[ReferralListItem])
def list_referrals(
    db: DbSession,
    user=require(Perm.REFERRALS_READ),
    status_: ReferralStatus | None = Query(None, alias="status"),
    direction: str = Query("all", pattern="^(all|incoming|outgoing)$"),
    pending_decision: bool = False,
    overdue: bool = Query(False, description="Rendez-vous dépassé sans réalisation : patientes à relancer"),
    limit: int = Query(100, le=500),
):
    accessible = scope_patients(select(Patient.id), user)
    q = (
        select(Referral, Patient, Screening)
        .join(Patient, Patient.id == Referral.patient_id)
        .join(Screening, Screening.id == Referral.screening_id)
        .where(Referral.patient_id.in_(accessible))
        .order_by(_SEVERITY, Referral.created_at.desc())
    )
    if status_:
        q = q.where(Referral.status == status_)
    if direction == "incoming":
        q = q.where(Referral.to_facility_id == user.facility_id)
    elif direction == "outgoing":
        q = q.where(Patient.facility_id == user.facility_id)
    if pending_decision:
        q = q.where(Referral.final_decision.is_(None))
    if overdue:
        q = q.where(
            Referral.status == ReferralStatus.SCHEDULED,
            Referral.appointment_date < date.today() - timedelta(days=LOST_TO_FOLLOW_UP_DAYS),
        )
    return [_item(r, p, s) for r, p, s in db.execute(q.limit(limit)).all()]


@router.post("/{referral_id}/decision", response_model=ReferralOut)
def decide(referral_id: int, body: ReferralDecision, db: DbSession, request: Request, user=require(Perm.REFERRALS_DECIDE)):
    """Le professionnel de santé confirme ou adapte la conduite à tenir proposée."""
    referral = _get(db, user, referral_id)
    if body.to_facility_id is not None and db.get(Facility, body.to_facility_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Établissement de référence inconnu")
    referral.final_decision = body.final_decision
    referral.to_facility_id = body.to_facility_id
    referral.reason = body.reason
    referral.appointment_date = body.appointment_date
    referral.decided_by_id = user.id
    referral.decided_at = utcnow()
    if body.to_facility_id and body.appointment_date:
        referral.status = ReferralStatus.SCHEDULED
    referral.screening.status = ScreeningStatus.VALIDATED
    audit(db, user, "decide", "referral", referral.id, {
        "proposed_level": referral.proposed_level.value if referral.proposed_level else None,
        "to_facility_id": body.to_facility_id,
    }, request)
    db.commit()
    return referral


@router.patch("/{referral_id}/status", response_model=ReferralOut)
def update_status(referral_id: int, body: ReferralStatusUpdate, db: DbSession, request: Request, user=require(Perm.REFERRALS_READ)):
    referral = _get(db, user, referral_id)
    if referral.final_decision is None and body.status in (ReferralStatus.SCHEDULED, ReferralStatus.COMPLETED):
        raise HTTPException(status.HTTP_409_CONFLICT, "L'orientation doit d'abord être validée par un professionnel de santé")
    referral.status = body.status
    if body.appointment_date:
        referral.appointment_date = body.appointment_date
    referral.completed_at = utcnow() if body.status == ReferralStatus.COMPLETED else None
    audit(db, user, "status_change", "referral", referral.id, {"status": body.status.value}, request)
    db.commit()
    return referral
