"""Restriction de l'accès aux dossiers selon l'établissement et le rôle."""

from fastapi import HTTPException, status
from sqlalchemy import Select, and_, or_, select
from sqlalchemy.orm import Session

from app.core.permissions import Role
from app.models import Patient, Referral, User


def incoming_to(facility_id: int):
    """Orientations « entrantes » d'une structure : celles où elle a été retenue par le médecin, et celles où elle
    est seulement proposée, tant qu'aucune décision n'a été prise (une décision sans référence lui retire l'accès)."""
    return or_(
        Referral.to_facility_id == facility_id,
        and_(Referral.final_decision.is_(None), Referral.to_facility_id.is_(None), Referral.proposed_facility_id == facility_id),
    )


def can_act_on_referral(user: User, referral: Referral, patient: Patient) -> bool:
    """Décider ou faire avancer une orientation : établissement de la patiente ou structure retenue.

    Une structure seulement proposée peut consulter le dossier pour se préparer, mais pas décider à la place du
    médecin qui suit la patiente.
    """
    return user.facility_id is not None and user.facility_id in (patient.facility_id, referral.to_facility_id)


def scope_patients(query: Select, user: User) -> Select:
    """Filtre une requête sur `Patient` aux dossiers accessibles par l'utilisateur.

    - agent de santé / médecin : patientes de leur établissement ;
    - spécialiste : patientes de son établissement et patientes qui y sont référées (ou proposées).
    """
    if user.facility_id is None:
        return query.where(False)
    if user.role == Role.SPECIALISTE:
        referred = select(Referral.patient_id).where(incoming_to(user.facility_id))
        return query.where(or_(Patient.facility_id == user.facility_id, Patient.id.in_(referred)))
    if user.role in (Role.AGENT, Role.MEDECIN):
        return query.where(Patient.facility_id == user.facility_id)
    return query.where(False)


def get_accessible_patient(db: Session, user: User, patient_id) -> Patient:
    patient = db.scalar(scope_patients(select(Patient).where(Patient.id == patient_id), user))
    if patient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patiente introuvable ou non accessible")
    return patient
