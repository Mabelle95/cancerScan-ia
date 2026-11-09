import base64
import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp())
os.environ.update({
    "DATABASE_URL": f"sqlite:///{(_tmp / 'test.db').as_posix()}",
    "DATA_ENCRYPTION_KEY": base64.b64encode(b"k" * 32).decode(),
    "LOOKUP_HMAC_KEY": "test-hmac",
    "JWT_SECRET": "test-secret-with-enough-length-for-hs256",
    "ENGINE_URL": "http://engine.invalid",
    "ENVIRONMENT": "test",
    "ADMIN_PASSWORD": "Password123!",
    "LOG_DIR": (_tmp / "logs").as_posix(),
})
LOG_FILE = _tmp / "logs" / "api.log"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402
from app.services import engine_client  # noqa: E402

PASSWORD = "Password123!"


@pytest.fixture(autouse=True)
def database():
    from app.services import login_guard
    login_guard.reset()  # compteur d'échecs par adresse IP : en mémoire, à remettre à zéro entre les tests
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    seed(demo=True)
    yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def login(client):
    def _login(email: str) -> dict:
        r = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}
    return _login


@pytest.fixture
def engine_ok(monkeypatch):
    """Moteur IA simulé : renvoie le niveau demandé par `engine_ok.level`."""
    calls = []

    class Fake:
        level = "faible"
        score = 0.05

        def __call__(self, pathology, features):
            calls.append((pathology, features))
            return {"model_id": f"{pathology}-test", "model_version": "0.0.1", "validated": False,
                    "score": self.score, "risk_level": self.level,
                    "explanations": [{"feature": "age", "contribution": 0.1}]}

    fake = Fake()
    fake.calls = calls
    monkeypatch.setattr(engine_client, "predict", fake)
    return fake


@pytest.fixture
def engine_down(monkeypatch):
    def _down(pathology, features):
        raise engine_client.EngineUnavailable("test")
    monkeypatch.setattr(engine_client, "predict", _down)
