from datetime import timedelta
from math import ceil

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.core.config import get_settings
from app.core.permissions import ROLE_PERMISSIONS, Role
from app.core.security import (
    create_access_token, dummy_verify, hash_password, password_problem, password_stamp, verify_password,
)
from app.deps import CurrentUser, DbSession
from app.models import User, as_utc, utcnow
from app.schemas import LoginIn, PasswordChangeIn, TokenOut, UserOut
from app.services import login_guard
from app.services.audit import audit

router = APIRouter(prefix="/auth", tags=["Authentification"])

INVALID = "Identifiants invalides"


def _minutes(seconds: float) -> int:
    return max(1, ceil(seconds / 60))


def _token(user: User) -> TokenOut:
    return TokenOut(
        access_token=create_access_token(str(user.id), user.role, password_stamp(user.password_changed_at)),
        expires_in=get_settings().access_token_minutes * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: DbSession, request: Request):
    settings = get_settings()
    ip = request.client.host if request.client else "?"
    email = body.email.lower()

    # 1. Trop d'échecs depuis cette adresse (essais sur plusieurs comptes)
    wait = login_guard.blocked_for(ip)
    if wait:
        audit(db, None, "login_throttled", "user", None, {"email": email}, request)
        db.commit()
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"Trop de tentatives de connexion depuis cet appareil. Réessayez dans {_minutes(wait)} min.")

    user = db.scalar(select(User).where(User.email == email))
    now = utcnow()

    # 2. Compte temporairement bloqué : refusé même avec le bon mot de passe
    locked_until = as_utc(user.locked_until) if user else None
    if user and locked_until and locked_until > now:
        dummy_verify(body.password)
        audit(db, user, "login_locked", "user", user.id, request=request)
        db.commit()
        raise HTTPException(
            status.HTTP_423_LOCKED,
            f"Compte temporairement bloqué après plusieurs échecs. Réessayez dans "
            f"{_minutes((locked_until - now).total_seconds())} min ou contactez votre administrateur.",
        )

    # 3. Vérification (même coût de calcul si le compte n'existe pas : le temps de réponse ne révèle rien)
    if user is None:
        dummy_verify(body.password)
        ok = False
    else:
        ok = verify_password(body.password, user.hashed_password) and user.is_active

    if not ok:
        login_guard.record_failure(ip)
        if user is not None:
            user.failed_login_count = (user.failed_login_count or 0) + 1
            if user.failed_login_count >= settings.login_max_failures:
                user.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
                user.failed_login_count = 0
                audit(db, user, "account_locked", "user", user.id,
                      {"minutes": settings.login_lock_minutes, "after_failures": settings.login_max_failures}, request)
        audit(db, user, "login_failed", "user", user.id if user else None, {"email": email}, request)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID)

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    login_guard.reset(ip)
    audit(db, user, "login", "user", user.id, request=request)
    db.commit()
    return _token(user)


@router.get("/me")
def me(user: CurrentUser):
    return {
        "user": UserOut.model_validate(user),
        "permissions": sorted(ROLE_PERMISSIONS[Role(user.role)]),
    }


@router.post("/change-password", response_model=TokenOut)
def change_password(body: PasswordChangeIn, user: CurrentUser, db: DbSession, request: Request):
    """Change le mot de passe ; les autres sessions sont déconnectées et un nouveau jeton est renvoyé."""
    if not verify_password(body.current_password, user.hashed_password):
        audit(db, user, "password_change_failed", "user", user.id, request=request)
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mot de passe actuel incorrect")
    problem = password_problem(body.new_password, user.email)
    if problem:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)
    if verify_password(body.new_password, user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Le nouveau mot de passe doit être différent de l'actuel.")
    user.hashed_password = hash_password(body.new_password)
    user.password_changed_at = utcnow()
    audit(db, user, "password_change", "user", user.id, request=request)
    db.commit()
    return _token(user)
