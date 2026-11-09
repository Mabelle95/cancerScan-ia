import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.core.permissions import Role
from app.models import ExamType, Pathology, ReferralStatus, RiskLevel, ScreeningStatus


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


# --- Authentification ---------------------------------------------------------

class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserOut"


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10)


# --- Établissements et utilisateurs -------------------------------------------

class FacilityIn(BaseModel):
    code: str = Field(max_length=32)
    name: str = Field(max_length=200)
    region: str = Field(max_length=100)
    district: str | None = None
    level: str | None = None
    is_active: bool = True


class FacilityOut(FacilityIn, ORM):
    id: int


class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(max_length=200)
    role: Role
    facility_id: int | None = None


class UserCreate(UserBase):
    password: str = Field(min_length=10)


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: Role | None = None
    facility_id: int | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=10)


class UserOut(UserBase, ORM):
    id: int
    is_active: bool
    mfa_enabled: bool
    created_at: datetime
    last_login_at: datetime | None


# --- Patientes ----------------------------------------------------------------

class PatientIn(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=30)
    birth_date: date | None = None
    birth_year_estimated: int | None = Field(default=None, ge=1900, le=2100)
    region: str = Field(max_length=100)
    locality: str | None = Field(default=None, max_length=150)
    education_level: str | None = None
    consent_given: bool
    consent_date: date | None = None
    consent_research: bool = False
    client_uuid: uuid.UUID | None = None

    @model_validator(mode="after")
    def _consent(self):
        if not self.consent_given:
            raise ValueError("Le consentement éclairé de la patiente est requis pour créer un dossier.")
        return self


class PatientUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    birth_date: date | None = None
    birth_year_estimated: int | None = None
    region: str | None = None
    locality: str | None = None
    education_level: str | None = None
    consent_research: bool | None = None


class PatientSummary(ORM):
    id: uuid.UUID
    code: str
    full_name: str | None
    birth_date: date | None
    birth_year_estimated: int | None
    region: str
    locality: str | None
    facility_id: int
    created_at: datetime


class PatientOut(PatientSummary):
    phone: str | None
    education_level: str | None
    consent_given: bool
    consent_date: date | None
    consent_research: bool
    client_uuid: uuid.UUID | None


class PatientCreated(BaseModel):
    patient: PatientOut
    possible_duplicates: list[PatientSummary] = []


# --- Dépistages ---------------------------------------------------------------

class ScreeningIn(BaseModel):
    pathology: Pathology
    data: dict[str, Any] = {}
    submit: bool = False
    client_uuid: uuid.UUID | None = None


class ScreeningUpdate(BaseModel):
    data: dict[str, Any]


class AssessmentOut(ORM):
    id: int
    model_id: str
    model_version: str
    model_validated: bool
    score: float
    risk_level: RiskLevel
    explanations: list
    created_at: datetime


class ReferralOut(ORM):
    id: int
    screening_id: uuid.UUID
    patient_id: uuid.UUID
    proposed_level: RiskLevel | None
    proposed_recommendation: str
    final_decision: str | None
    decided_by_id: int | None
    decided_at: datetime | None
    to_facility_id: int | None
    reason: str | None
    appointment_date: date | None
    status: ReferralStatus
    created_at: datetime
    completed_at: datetime | None


class ScreeningOut(ORM):
    id: uuid.UUID
    patient_id: uuid.UUID
    pathology: Pathology
    form_version: str
    status: ScreeningStatus
    data: dict
    alerts: list
    facility_id: int
    created_at: datetime
    submitted_at: datetime | None
    client_uuid: uuid.UUID | None
    assessments: list[AssessmentOut] = []
    referral: ReferralOut | None = None


class SubmitResult(BaseModel):
    screening: ScreeningOut
    missing_required: list[str] = []
    errors: dict[str, str] = {}
    ai_pending: bool = False


# --- Orientations et examens --------------------------------------------------

class ReferralDecision(BaseModel):
    final_decision: str = Field(min_length=3)
    to_facility_id: int | None = None
    reason: str | None = None
    appointment_date: date | None = None


class ReferralStatusUpdate(BaseModel):
    status: ReferralStatus
    appointment_date: date | None = None


class ReferralListItem(ReferralOut):
    patient_code: str
    pathology: Pathology


class ExamIn(BaseModel):
    screening_id: uuid.UUID | None = None
    exam_type: ExamType
    result: str = Field(min_length=1)
    conclusion: str | None = Field(default=None, pattern="^(normal|benin|suspect|malin|precancereux|indetermine)$")
    exam_date: date | None = None
    source: str | None = None


class ExamOut(ExamIn, ORM):
    id: int
    patient_id: uuid.UUID
    recorded_by_id: int
    created_at: datetime


# --- Synchronisation hors ligne -----------------------------------------------

class SyncScreening(ScreeningIn):
    client_uuid: uuid.UUID


class SyncPatient(PatientIn):
    client_uuid: uuid.UUID
    screenings: list[SyncScreening] = []


class SyncExistingScreening(SyncScreening):
    """Dépistage saisi hors ligne pour une patiente déjà connue du serveur."""

    patient_id: uuid.UUID


class SyncIn(BaseModel):
    patients: list[SyncPatient] = []
    screenings: list[SyncExistingScreening] = []


class SyncItemResult(BaseModel):
    client_uuid: uuid.UUID
    server_id: uuid.UUID | None = None
    status: str  # created, already_synced, error
    detail: str | None = None


class SyncOut(BaseModel):
    patients: list[SyncItemResult]
    screenings: list[SyncItemResult]


class AuditOut(ORM):
    id: int
    user_id: int | None
    action: str
    entity: str
    entity_id: str | None
    details: dict
    ip_address: str | None
    created_at: datetime


TokenOut.model_rebuild()
