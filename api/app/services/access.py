"""Restriction de l'accès aux dossiers selon l'établissement et le rôle."""

from fastapi import HTTPException, status
from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from app.core.permissions import Role
from app.models import Patient, Referral, User


def scope_patients(query: Select, user: User) -> Select:
    """Filtre une requête sur `Patient` aux dossiers accessibles par l'utilisateur.

    - agent de santé / médecin : patientes de leur établissement ;
    - spécialiste : patientes de son établissement et patientes qui y sont référées (ou proposées).
    """
    if user.facility_id is None:
        return query.where(False)
    if user.role == Role.SPECIALISTE:
        referred = select(Referral.patient_id).where(or_(
            Referral.to_facility_id == user.facility_id,
            # orientation proposée vers cette structure, pas encore confirmée par un médecin
            (Referral.to_facility_id.is_(None)) & (Referral.proposed_facility_id == user.facility_id),
        ))
        return query.where(or_(Patient.facility_id == user.facility_id, Patient.id.in_(referred)))
    if user.role in (Role.AGENT, Role.MEDECIN):
        return query.where(Patient.facility_id == user.facility_id)
    return query.where(False)


def get_accessible_patient(db: Session, user: User, patient_id) -> Patient:
    patient = db.scalar(scope_patients(select(Patient).where(Patient.id == patient_id), user))
    if patient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patiente introuvable ou non accessible")
    return patient
