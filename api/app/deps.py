from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.permissions import Perm, has_permission
from app.core.security import decode_access_token, password_stamp
from app.db import get_db
from app.models import User

bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentification requise", {"WWW-Authenticate": "Bearer"})
    if credentials is None:
        raise unauthorized
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.PyJWTError:
        raise unauthorized
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise unauthorized
    if payload.get("pwd", 0) != password_stamp(user.password_changed_at):
        # Jeton émis avant le dernier changement de mot de passe : session révoquée
        raise unauthorized
    request.state.user_id = user.id  # pour le journal d'accès et l'enregistrement des erreurs
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require(perm: Perm):
    def checker(user: CurrentUser) -> User:
        if not has_permission(user.role, perm):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Permission insuffisante")
        return user

    return Depends(checker)
