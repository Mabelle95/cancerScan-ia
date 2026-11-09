from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.core.config import get_settings
from app.core.permissions import ROLE_PERMISSIONS, Role
from app.core.security import create_access_token, hash_password, verify_password
from app.deps import CurrentUser, DbSession
from app.models import User, utcnow
from app.schemas import LoginIn, PasswordChangeIn, TokenOut, UserOut
from app.services.audit import audit

router = APIRouter(prefix="/auth", tags=["Authentification"])


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: DbSession, request: Request):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not user.is_active or not verify_password(body.password, user.hashed_password):
        audit(db, user, "login_failed", "user", user.id if user else None, {"email": body.email}, request)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Identifiants invalides")
    user.last_login_at = utcnow()
    audit(db, user, "login", "user", user.id, request=request)
    db.commit()
    return TokenOut(
        access_token=create_access_token(str(user.id), user.role),
        expires_in=get_settings().access_token_minutes * 60,
        user=UserOut.model_validate(user),
    )


@router.get("/me")
def me(user: CurrentUser):
    return {
        "user": UserOut.model_validate(user),
        "permissions": sorted(ROLE_PERMISSIONS[Role(user.role)]),
    }


@router.post("/change-password", status_code=204)
def change_password(body: PasswordChangeIn, user: CurrentUser, db: DbSession, request: Request):
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mot de passe actuel incorrect")
    user.hashed_password = hash_password(body.new_password)
    audit(db, user, "password_change", "user", user.id, request=request)
    db.commit()
