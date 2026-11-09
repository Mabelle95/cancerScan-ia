import hashlib
import hmac
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings


# Empreinte factice : vérifiée quand le compte n'existe pas, pour que le temps de réponse ne révèle rien.
_DUMMY_HASH = bcrypt.hashpw(b"compte-inexistant", bcrypt.gensalt()).decode()

# Mots de passe trop courants (extrait) : refusés même s'ils respectent la longueur
_COMMON = {"password123", "motdepasse", "motdepasse1", "azerty1234", "azertyuiop", "qwerty1234", "1234567890",
           "0123456789", "cancerscan", "cancerscan1", "administrateur", "changeme123", "bonjour123", "togo123456"}


def password_problem(password: str, email: str | None = None) -> str | None:
    """Règles minimales (à adapter à la politique de sécurité du ministère). None si le mot de passe convient."""
    if len(password) < 10:
        return "Le mot de passe doit contenir au moins 10 caractères."
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        return "Le mot de passe doit contenir des lettres et des chiffres."
    if password.lower() in _COMMON or len(set(password)) < 5:
        return "Ce mot de passe est trop courant ou trop simple."
    if email and email.split("@")[0].lower() in password.lower():
        return "Le mot de passe ne doit pas contenir votre identifiant."
    return None


def dummy_verify(password: str) -> None:
    bcrypt.checkpw(password.encode(), _DUMMY_HASH.encode())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def password_stamp(changed_at: datetime | None) -> int:
    """Version du mot de passe inscrite dans le jeton : un changement invalide tous les jetons émis avant."""
    if changed_at is None:
        return 0
    if changed_at.tzinfo is None:
        changed_at = changed_at.replace(tzinfo=timezone.utc)
    return int(changed_at.timestamp() * 1_000_000)


def create_access_token(subject: str, role: str, pwd_stamp: int = 0) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "role": role,
        "pwd": pwd_stamp,
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
