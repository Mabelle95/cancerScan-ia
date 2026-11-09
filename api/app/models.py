import uuid
from datetime import date, datetime, timezone
from enum import StrEnum

from sqlalchemy import JSON, Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.crypto import EncryptedString
from app.core.permissions import Role
from app.db import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def enum_column(enum_cls: type[StrEnum]) -> Enum:
    return Enum(enum_cls, native_enum=False, length=32, values_callable=lambda e: [m.value for m in e])


class Pathology(StrEnum):
    SEIN = "sein"
    COL = "col"
    OVAIRE = "ovaire"
    ENDOMETRE = "endometre"


class ScreeningStatus(StrEnum):
    DRAFT = "brouillon"
    SUBMITTED = "soumis"        # validé, en attente du calcul IA (ex. moteur indisponible)
    ANALYSED = "analyse"        # score IA calculé, orientation proposée
    VALIDATED = "valide"        # conduite à tenir validée par un professionnel


class RiskLevel(StrEnum):
    FAIBLE = "faible"
    MOYEN = "moyen"
    ELEVE = "eleve"


class ReferralStatus(StrEnum):
    PROPOSED = "proposee"
    SCHEDULED = "programmee"
    COMPLETED = "realisee"
    LOST = "perdue_de_vue"
    CANCELLED = "annulee"


class ExamType(StrEnum):
    MAMMOGRAPHIE = "mammographie"
    ECHOGRAPHIE_MAMMAIRE = "echographie_mammaire"
    ECHOGRAPHIE_PELVIENNE = "echographie_pelvienne"
    CYTOLOGIE = "cytologie"
    TEST_HPV = "test_hpv"
    BIOPSIE = "biopsie"
    AUTRE = "autre"


class Facility(Base):
    __tablename__ = "facilities"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    region: Mapped[str] = mapped_column(String(100), index=True)
    district: Mapped[str | None] = mapped_column(String(100))
    level: Mapped[str | None] = mapped_column(String(50))  # USP, CMS, CHP, CHR, CHU…
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(enum_column(Role))
    facility_id: Mapped[int | None] = mapped_column(ForeignKey("facilities.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    facility: Mapped[Facility | None] = relationship()


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)  # identifiant lisible, ex. CS-LOM-000123
    birth_date: Mapped[date | None] = mapped_column(Date)
    birth_year_estimated: Mapped[int | None] = mapped_column(Integer)  # quand la date exacte est inconnue
    region: Mapped[str] = mapped_column(String(100), index=True)
    locality: Mapped[str | None] = mapped_column(String(150))
    education_level: Mapped[str | None] = mapped_column(String(50))
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), index=True)

    # Données identifiantes : chiffrées, jamais transmises au moteur IA
    full_name: Mapped[str | None] = mapped_column(EncryptedString(512))
    phone: Mapped[str | None] = mapped_column(EncryptedString(256))
    phone_lookup: Mapped[str | None] = mapped_column(String(64), index=True)

    consent_given: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_date: Mapped[date | None] = mapped_column(Date)
    consent_research: Mapped[bool] = mapped_column(Boolean, default=False)

    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Identifiant généré côté mobile pour rendre la synchronisation hors ligne idempotente
    client_uuid: Mapped[uuid.UUID | None] = mapped_column(Uuid, unique=True)

    facility: Mapped[Facility] = relationship()
    screenings: Mapped[list["Screening"]] = relationship(back_populates="patient", order_by="Screening.created_at.desc()")


class Screening(Base):
    __tablename__ = "screenings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"), index=True)
    pathology: Mapped[Pathology] = mapped_column(enum_column(Pathology))
    form_version: Mapped[str] = mapped_column(String(20))
    status: Mapped[ScreeningStatus] = mapped_column(enum_column(ScreeningStatus), default=ScreeningStatus.DRAFT)
    data: Mapped[dict] = mapped_column(JsonType, default=dict)
    alerts: Mapped[list] = mapped_column(JsonType, default=list)  # signes d'alerte détectés dans la saisie
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    client_uuid: Mapped[uuid.UUID | None] = mapped_column(Uuid, unique=True)

    patient: Mapped[Patient] = relationship(back_populates="screenings")
    assessments: Mapped[list["RiskAssessment"]] = relationship(back_populates="screening", order_by="RiskAssessment.created_at.desc()")
    referral: Mapped["Referral | None"] = relationship(back_populates="screening", uselist=False)


class RiskAssessment(Base):
    """Résultat d'une exécution du moteur IA, conservé pour la traçabilité."""

    __tablename__ = "risk_assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    screening_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("screenings.id"), index=True)
    pathology: Mapped[Pathology] = mapped_column(enum_column(Pathology))
    model_id: Mapped[str] = mapped_column(String(100))
    model_version: Mapped[str] = mapped_column(String(50))
    model_validated: Mapped[bool] = mapped_column(Boolean, default=False)
    score: Mapped[float] = mapped_column(Float)
    risk_level: Mapped[RiskLevel] = mapped_column(enum_column(RiskLevel))
    explanations: Mapped[list] = mapped_column(JsonType, default=list)
    features_sent: Mapped[dict] = mapped_column(JsonType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    screening: Mapped[Screening] = relationship(back_populates="assessments")


class Referral(Base):
    """Orientation : proposition issue de l'analyse, puis décision du professionnel et suivi."""

    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(primary_key=True)
    screening_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("screenings.id"), unique=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"), index=True)
    proposed_level: Mapped[RiskLevel | None] = mapped_column(enum_column(RiskLevel))
    proposed_recommendation: Mapped[str] = mapped_column(Text)
    final_decision: Mapped[str | None] = mapped_column(Text)
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    to_facility_id: Mapped[int | None] = mapped_column(ForeignKey("facilities.id"), index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    appointment_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[ReferralStatus] = mapped_column(enum_column(ReferralStatus), default=ReferralStatus.PROPOSED)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    screening: Mapped[Screening] = relationship(back_populates="referral")
    to_facility: Mapped[Facility | None] = relationship()


class ExamResult(Base):
    __tablename__ = "exam_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"), index=True)
    screening_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("screenings.id"))
    exam_type: Mapped[ExamType] = mapped_column(enum_column(ExamType))
    result: Mapped[str] = mapped_column(Text)
    conclusion: Mapped[str | None] = mapped_column(String(50))  # normal, benin, suspect, malin, indetermine
    exam_date: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str | None] = mapped_column(String(200))  # laboratoire / service ayant produit le résultat
    recorded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(50), index=True)  # login, read, create, update, ai_run, …
    entity: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JsonType, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ErrorEvent(Base):
    """Erreur technique (API, moteur IA, site Web, application mobile) pour la supervision.

    Ne contient jamais de données de patiente : message et trace technique tronqués uniquement.
    """

    __tablename__ = "system_errors"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(20), index=True)  # api, engine, web, mobile
    level: Mapped[str] = mapped_column(String(10), default="error")
    message: Mapped[str] = mapped_column(String(1000))
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    path: Mapped[str | None] = mapped_column(String(300))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    details: Mapped[dict] = mapped_column(JsonType, default=dict)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
