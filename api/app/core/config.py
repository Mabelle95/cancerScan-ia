from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(ROOT_DIR / ".env", ".env"), extra="ignore")

    app_name: str = "CancerScan API"
    environment: str = "development"

    database_url: str = "postgresql+psycopg://cancerscan:cancerscan@localhost:5432/cancerscan"

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60

    # AES-256-GCM : 32 octets encodés en base64
    data_encryption_key: str = ""
    lookup_hmac_key: str = "change-me"

    engine_url: str = "http://localhost:8001"
    engine_api_key: str = "change-me"
    engine_timeout_seconds: float = 10.0

    forms_dir: Path = ROOT_DIR / "shared" / "forms"
    cors_origins: list[str] = ["http://localhost:5173"]

    # Les effectifs inférieurs à ce seuil sont masqués dans les statistiques agrégées
    stats_min_cell_size: int = 5

    # Protection de la connexion : blocage du compte après N échecs consécutifs, limite par adresse IP
    login_max_failures: int = 5
    login_lock_minutes: int = 15
    login_ip_max_failures: int = 20
    login_ip_window_minutes: int = 15

    # Logs : JSON sur la console et dans un fichier tournant (vide = console uniquement)
    log_dir: Path | None = ROOT_DIR / "logs"
    log_level: str = "INFO"

    admin_email: str = "admin@cancerscan.tg"
    admin_password: str = "ChangeMe123!"


@lru_cache
def get_settings() -> Settings:
    return Settings()
