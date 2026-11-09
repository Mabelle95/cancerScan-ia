"""Chiffrement applicatif AES-256-GCM des champs sensibles."""

import base64
import os
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import String, TypeDecorator

from app.core.config import get_settings

_NONCE_SIZE = 12


@lru_cache
def _cipher() -> AESGCM:
    raw = get_settings().data_encryption_key
    if not raw:
        raise RuntimeError("DATA_ENCRYPTION_KEY manquante : impossible de chiffrer les données sensibles.")
    key = base64.b64decode(raw)
    if len(key) != 32:
        raise RuntimeError("DATA_ENCRYPTION_KEY doit faire 32 octets (AES-256).")
    return AESGCM(key)


def encrypt(plaintext: str) -> str:
    nonce = os.urandom(_NONCE_SIZE)
    return base64.b64encode(nonce + _cipher().encrypt(nonce, plaintext.encode(), None)).decode()


def decrypt(token: str) -> str:
    data = base64.b64decode(token)
    return _cipher().decrypt(data[:_NONCE_SIZE], data[_NONCE_SIZE:], None).decode()


class EncryptedString(TypeDecorator):
    """Colonne texte chiffrée de manière transparente à l'écriture et déchiffrée à la lecture."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else encrypt(value)

    def process_result_value(self, value, dialect):
        return None if value is None else decrypt(value)
