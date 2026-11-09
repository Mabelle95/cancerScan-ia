from datetime import timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.db import SessionLocal
from app.models import AuditLog, User, utcnow
from tests.conftest import PASSWORD

API = "/api/v1"
AGENT = "agent@cancerscan.tg"


def _login(client, email=AGENT, password=PASSWORD):
    return client.post(f"{API}/auth/login", json={"email": email, "password": password})


def _actions():
    with SessionLocal() as db:
        return [a for a in db.scalars(select(AuditLog.action).order_by(AuditLog.id))]


def test_account_locked_after_repeated_failures(client):
    for _ in range(get_settings().login_max_failures):
        assert _login(client, password="mauvais-mot-2-passe").status_code == 401
    # Bloqué : même le bon mot de passe est refusé, avec un message clair
    r = _login(client)
    assert r.status_code == 423 and "bloqué" in r.json()["detail"]
    assert "account_locked" in _actions() and "login_locked" in _actions()


def test_lock_expires_and_success_resets_counter(client):
    for _ in range(get_settings().login_max_failures):
        _login(client, password="mauvais-mot-2-passe")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == AGENT))
        user.locked_until = utcnow() - timedelta(seconds=1)  # le blocage est expiré
        db.commit()
    assert _login(client).status_code == 200
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == AGENT))
        assert user.failed_login_count == 0 and user.locked_until is None


def test_failures_below_threshold_do_not_lock(client):
    for _ in range(get_settings().login_max_failures - 1):
        _login(client, password="mauvais-mot-2-passe")
    assert _login(client).status_code == 200


def test_unknown_accounts_get_same_answer_and_ip_is_throttled(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "login_ip_max_failures", 3)
    r = _login(client, email="inconnu@cancerscan.tg")
    assert r.status_code == 401 and r.json()["detail"] == _login(client, password="faux-mot-2-passe").json()["detail"]
    _login(client, email="autre@cancerscan.tg")
    r = _login(client)  # 3 échecs depuis cette adresse : même un bon mot de passe doit attendre
    assert r.status_code == 429 and "Réessayez" in r.json()["detail"]
    assert "login_throttled" in _actions()


def test_admin_can_unlock(client, login):
    for _ in range(get_settings().login_max_failures):
        _login(client, password="mauvais-mot-2-passe")
    admin = login("admin@cancerscan.tg")
    users = client.get(f"{API}/users", headers=admin).json()
    agent = next(u for u in users if u["email"] == AGENT)
    assert agent["locked_until"] is not None
    medecin = login("medecin@cancerscan.tg")
    assert client.post(f"{API}/users/{agent['id']}/unlock", headers=medecin).status_code == 403
    assert client.post(f"{API}/users/{agent['id']}/unlock", headers=admin).json()["locked_until"] is None
    assert _login(client).status_code == 200
    assert "account_unlocked" in _actions()


def test_weak_passwords_rejected(client, login):
    admin = login("admin@cancerscan.tg")
    for weak, why in [("courtmdp1", "10 caractères"), ("seulementdeslettres", "lettres et des chiffres"),
                      ("azerty1234", "trop courant"), ("nouvel.agent2026", "identifiant")]:
        r = client.post(f"{API}/users", headers=admin, json={"email": "nouvel.agent@cancerscan.tg", "full_name": "Test",
                                                            "role": "agent_sante", "facility_id": 1, "password": weak})
        assert r.status_code in (400, 422) and (why in str(r.json()["detail"]) or r.status_code == 422), weak
    ok = client.post(f"{API}/users", headers=admin, json={"email": "nouvel.agent@cancerscan.tg", "full_name": "Test",
                                                         "role": "agent_sante", "facility_id": 1, "password": "Kpalime-Plateaux-27"})
    assert ok.status_code == 201


def test_password_change_revokes_other_sessions(client, login):
    old = login(AGENT)
    other_device = login(AGENT)
    r = client.post(f"{API}/auth/change-password", headers=old,
                    json={"current_password": PASSWORD, "new_password": "Nouveau-Secret-2027"})
    assert r.status_code == 200
    fresh = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get(f"{API}/auth/me", headers=fresh).status_code == 200      # la session courante continue
    assert client.get(f"{API}/auth/me", headers=other_device).status_code == 401  # les autres sont déconnectées
    assert _login(client).status_code == 401
    assert _login(client, password="Nouveau-Secret-2027").status_code == 200


def test_password_change_requires_current_and_strong_password(client, login):
    h = login(AGENT)
    r = client.post(f"{API}/auth/change-password", headers=h, json={"current_password": "faux", "new_password": "Nouveau-Secret-2027"})
    assert r.status_code == 400 and "actuel" in r.json()["detail"]
    r = client.post(f"{API}/auth/change-password", headers=h, json={"current_password": PASSWORD, "new_password": "aaaaaaaaaa1"})
    assert r.status_code == 400
