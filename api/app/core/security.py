import hashlib
import hmac
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_access_token(subject: str, role: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def lookup_hash(value: str) -> str:
    """HMAC déterministe pour rechercher une valeur chiffrée (ex. doublons de téléphone)."""
    # Numéros togolais : 8 chiffres nationaux ; l'indicatif +228 / 00228 est ignoré pour que les deux saisies correspondent.
    normalized = "".join(ch for ch in value if ch.isdigit())[-8:]
    key = get_settings().lookup_hmac_key.encode()
    return hmac.new(key, normalized.encode(), hashlib.sha256).hexdigest()
