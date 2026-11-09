import logging

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import ErrorEvent, Screening
from app.services import engine_client
from tests.conftest import LOG_FILE

API = "/api/v1"


def _boom():
    raise RuntimeError("panne simulée")


app.add_api_route(f"{API}/_test/boom", _boom, methods=["GET"])


def _flush_logs():
    for h in logging.getLogger().handlers:
        h.flush()


def test_request_id_generated_and_propagated(client):
    r = client.get("/health")
    assert len(r.headers["x-request-id"]) >= 8
    r = client.get("/health", headers={"X-Request-ID": "abc123def456"})
    assert r.headers["x-request-id"] == "abc123def456"
    # Un identifiant fourni malformé est remplacé (pas d'injection dans les logs)
    r = client.get("/health", headers={"X-Request-ID": "x\ny {bad}"})
    assert r.headers["x-request-id"] != "x\ny {bad}"


def test_unhandled_error_returns_reference_and_is_recorded():
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get(f"{API}/_test/boom")
    assert r.status_code == 500
    rid = r.json()["request_id"]
    assert rid in r.json()["detail"] and "panne simulée" not in r.json()["detail"]  # aucun détail technique exposé
    with SessionLocal() as db:
        event = db.scalar(select(ErrorEvent).where(ErrorEvent.request_id == rid))
    assert event.source == "api" and "RuntimeError" in event.message and "Traceback" in event.details["traceback"]


def test_logs_never_contain_search_terms_or_identities(client, login):
    h = login("agent@cancerscan.tg")
    client.post(f"{API}/patients", headers=h, json={"full_name": "Yawa Secretnom", "phone": "+228 91 23 45 67",
                                                   "region": "Maritime", "consent_given": True})
    client.get(f"{API}/patients", params={"q": "Secretnom"}, headers=h)
    client.get(f"{API}/patients", params={"q": "91234567"}, headers=h)
    _flush_logs()
    content = LOG_FILE.read_text(encoding="utf-8")
    assert '"path": "/api/v1/patients"' in content
    assert "Secretnom" not in content and "91234567" not in content and "91 23 45 67" not in content
    assert '"user_id": 2' in content  # l'auteur de la requête est tracé


def test_validation_errors_in_french(client):
    r = client.post(f"{API}/auth/login", json={"email": "pas-un-email", "password": "x"})
    assert r.status_code == 422
    assert r.json()["detail"][0]["msg"] == "Adresse e-mail invalide"
    r = client.post(f"{API}/auth/login", json={"email": "a@b.tg"})
    assert r.json()["detail"][0]["msg"] == "Mot de passe : Champ obligatoire"


def test_client_error_report_and_admin_status(client, login):
    agent = login("agent@cancerscan.tg")
    r = client.post(f"{API}/client-errors", headers=agent,
                    json={"source": "mobile", "message": "StateError: boom", "app_version": "0.1.0", "screen": "wizard"})
    assert r.status_code == 202
    admin = login("admin@cancerscan.tg")
    errors = client.get(f"{API}/system/errors", headers=admin, params={"source": "mobile"}).json()
    assert errors[0]["message"] == "StateError: boom" and errors[0]["user_id"] == 2
    client.post(f"{API}/system/errors/{errors[0]['id']}/resolve", headers=admin)
    assert client.get(f"{API}/system/errors", headers=admin, params={"source": "mobile"}).json() == []

    status = client.get(f"{API}/system/status", headers=admin).json()
    assert status["database"]["status"] == "ok"
    assert status["engine"]["status"] == "injoignable" and status["status"] == "degrade"  # pas de moteur en test
    assert status["api"]["requests"] > 0
    assert client.get(f"{API}/system/status", headers=agent).status_code == 403


def test_engine_server_error_defers_analysis(client, login, monkeypatch):
    def fake_post(*args, **kwargs):
        return httpx.Response(500, text="Traceback interne", request=httpx.Request("POST", "http://engine/predict"))
    monkeypatch.setattr(engine_client.httpx, "post", fake_post)
    h = login("agent@cancerscan.tg")
    pid = client.post(f"{API}/patients", headers=h, json={"region": "Kara", "consent_given": True}).json()["patient"]["id"]
    data = {"atcd_familial_sein_ovaire": False, "atcd_personnel_sein": False, "masse_presente": False, "modif_peau": False,
            "retraction_mamelon": False, "examen_realise": False, "probabilite_enqueteur": "faible"}
    r = client.post(f"{API}/patients/{pid}/screenings", headers=h, json={"pathology": "sein", "data": data, "submit": True})
    assert r.status_code == 201 and r.json()["ai_pending"] is True  # la saisie n'est pas perdue
    with SessionLocal() as db:
        assert db.scalar(select(ErrorEvent).where(ErrorEvent.source == "engine")) is not None
        assert db.scalar(select(Screening)).status == "soumis"
