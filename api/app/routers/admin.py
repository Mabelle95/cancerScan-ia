"""Administration : utilisateurs, établissements, journal d'activité et modèles IA."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import select

from app.core.permissions import Perm
from app.core.security import hash_password, password_problem
from app.deps import CurrentUser, DbSession, require
from app.models import AuditLog, Facility, User, utcnow
from app.schemas import AuditOut, FacilityIn, FacilityOut, UserCreate, UserOut, UserUpdate
from app.services import engine_client
from app.services.audit import audit

router = APIRouter(tags=["Administration"])


# --- Établissements (lecture ouverte à tout utilisateur connecté : nécessaire pour les références)

@router.get("/facilities", response_model=list[FacilityOut])
def list_facilities(db: DbSession, _: CurrentUser, region: str | None = None, active_only: bool = True):
    q = select(Facility).order_by(Facility.region, Facility.name)
    if region:
        q = q.where(Facility.region == region)
    if active_only:
        q = q.where(Facility.is_active.is_(True))
    return db.scalars(q).all()


@router.post("/facilities", response_model=FacilityOut, status_code=201)
def create_facility(body: FacilityIn, db: DbSession, request: Request, user=require(Perm.FACILITIES_MANAGE)):
    if db.scalar(select(Facility).where(Facility.code == body.code)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Code d'établissement déjà utilisé")
    facility = Facility(**body.model_dump())
    db.add(facility)
    db.flush()
    audit(db, user, "create", "facility", facility.id, request=request)
    db.commit()
    return facility


@router.put("/facilities/{facility_id}", response_model=FacilityOut)
def update_facility(facility_id: int, body: FacilityIn, db: DbSession, request: Request, user=require(Perm.FACILITIES_MANAGE)):
    facility = db.get(Facility, facility_id) or _not_found("Établissement")
    for k, v in body.model_dump().items():
        setattr(facility, k, v)
    audit(db, user, "update", "facility", facility.id, request=request)
    db.commit()
    return facility


# --- Utilisateurs

@router.get("/users", response_model=list[UserOut])
def list_users(db: DbSession, _=require(Perm.USERS_MANAGE), role: str | None = None, facility_id: int | None = None):
    q = select(User).order_by(User.full_name)
    if role:
        q = q.where(User.role == role)
    if facility_id:
        q = q.where(User.facility_id == facility_id)
    return db.scalars(q).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, db: DbSession, request: Request, admin=require(Perm.USERS_MANAGE)):
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Adresse e-mail déjà utilisée")
    _check_facility(db, body.facility_id)
    problem = password_problem(body.password, email)
    if problem:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)
    user = User(email=email, full_name=body.full_name, role=body.role, facility_id=body.facility_id,
                hashed_password=hash_password(body.password))
    db.add(user)
    db.flush()
    audit(db, admin, "create", "user", user.id, {"role": body.role.value}, request)
    db.commit()
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, db: DbSession, request: Request, admin=require(Perm.USERS_MANAGE)):
    user = db.get(User, user_id) or _not_found("Utilisateur")
    changes = body.model_dump(exclude_unset=True)
    if user.id == admin.id and (changes.get("is_active") is False or ("role" in changes and changes["role"] != user.role)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Un administrateur ne peut pas se désactiver ni changer son propre rôle")
    if "facility_id" in changes:
        _check_facility(db, changes["facility_id"])
    password = changes.pop("password", None)
    if password:
        problem = password_problem(password, user.email)
        if problem:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)
        user.hashed_password = hash_password(password)
        user.password_changed_at = utcnow()  # les sessions ouvertes avec l'ancien mot de passe sont révoquées
        user.locked_until, user.failed_login_count = None, 0
    for k, v in changes.items():
        setattr(user, k, v)
    # Les changements de droits sont journalisés explicitement (cahier des charges §11.3)
    action = "rights_change" if {"role", "is_active", "facility_id"} & changes.keys() else "update"
    audit(db, admin, action, "user", user.id, {k: str(v) for k, v in changes.items()} | ({"password": "reset"} if password else {}), request)
    db.commit()
    return user


@router.post("/users/{user_id}/unlock", response_model=UserOut)
def unlock_user(user_id: int, db: DbSession, request: Request, admin=require(Perm.USERS_MANAGE)):
    """Débloque un compte bloqué après des échecs de connexion répétés."""
    user = db.get(User, user_id) or _not_found("Utilisateur")
    user.locked_until, user.failed_login_count = None, 0
    audit(db, admin, "account_unlocked", "user", user.id, request=request)
    db.commit()
    return user


# --- Journal d'activité

@router.get("/audit", response_model=list[AuditOut])
def list_audit(
    db: DbSession,
    _=require(Perm.AUDIT_READ),
    user_id: int | None = None,
    action: str | None = None,
    entity: str | None = None,
    since: datetime | None = None,
    limit: int = Query(200, le=1000),
    offset: int = 0,
):
    q = select(AuditLog).order_by(AuditLog.created_at.desc())
    if user_id:
        q = q.where(AuditLog.user_id == user_id)
    if action:
        q = q.where(AuditLog.action == action)
    if entity:
        q = q.where(AuditLog.entity == entity)
    if since:
        q = q.where(AuditLog.created_at >= since)
    return db.scalars(q.limit(limit).offset(offset)).all()


# --- Modèles IA déployés

@router.get("/models")
def list_models(_=require(Perm.MODELS_MANAGE)):
    try:
        return engine_client.list_models()
    except engine_client.EngineUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))


def _check_facility(db, facility_id: int | None) -> None:
    if facility_id is not None and db.get(Facility, facility_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Établissement inconnu")


def _not_found(what: str):
    raise HTTPException(status.HTTP_404_NOT_FOUND, f"{what} introuvable")
