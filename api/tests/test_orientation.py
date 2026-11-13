"""Orientation vers la structure spécialisée la plus proche."""

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Facility, Pathology
from app.services.directory import distance_km, nearest_specialists

from tests.test_workflow import API, SEIN_COMPLET, _new_patient


def _screen(client, headers, pid, engine_ok, level):
    engine_ok.level, engine_ok.score = level, 0.8 if level == "eleve" else 0.1
    r = client.post(f"{API}/patients/{pid}/screenings",
                    json={"pathology": "sein", "data": SEIN_COMPLET, "submit": True}, headers=headers)
    assert r.status_code in (200, 201), r.text
    return r.json()["screening"]


def test_distance_km():
    # Lomé → Kara : environ 380 km à vol d'oiseau
    assert 370 < distance_km(6.1319, 1.2228, 9.5511, 1.1861) < 390


def test_high_risk_proposes_nearest_specialist(client, login, engine_ok):
    agent = login("agent@cancerscan.tg")  # centre de santé de Lomé, sans spécialiste
    pid = _new_patient(client, agent)["patient"]["id"]
    ref = _screen(client, agent, pid, engine_ok, "eleve")["referral"]

    names = [f["name"] for f in ref["suggested_facilities"]]
    assert names[0] == "CHU démo Lomé (référence)"  # la plus proche qui a une consultation du sein
    assert "Centre de santé démo Lomé" not in names  # pas de service spécialisé : jamais proposé
    first = ref["suggested_facilities"][0]
    assert first["distance_km"] < 10 and first["phone"]
    assert "mammographie" in first["services"]
    assert ref["proposed_facility_id"] == first["facility_id"]
    distances = [f["distance_km"] for f in ref["suggested_facilities"]]
    assert distances == sorted(distances)


def test_low_risk_has_no_referral_facility(client, login, engine_ok):
    agent = login("agent@cancerscan.tg")
    pid = _new_patient(client, agent)["patient"]["id"]
    ref = _screen(client, agent, pid, engine_ok, "faible")["referral"]
    assert ref["suggested_facilities"] == [] and ref["proposed_facility_id"] is None


def test_nearest_depends_on_where_the_patient_is():
    with SessionLocal() as db:
        kara = db.scalar(select(Facility).where(Facility.code == "KAR01"))
        dapaong = db.scalar(select(Facility).where(Facility.code == "DAP-CHR"))
        assert nearest_specialists(db, Pathology.SEIN, kara)[0]["name"] == "CHU démo Kara (référence)"
        # Pour le col, une consultation de gynécologie suffit : Dapaong se propose elle-même
        col = nearest_specialists(db, Pathology.COL, dapaong)
        assert col[0]["name"] == "CHR démo Dapaong" and col[0]["same_facility"] and col[0]["distance_km"] == 0
        # Établissement sans coordonnées : la même région passe en premier
        kara.latitude = kara.longitude = None
        assert nearest_specialists(db, Pathology.SEIN, kara)[0]["region"] == "Kara"
        db.rollback()


def test_proposed_facility_sees_incoming_patient(client, login, engine_ok):
    agent = login("agent@cancerscan.tg")
    pid = _new_patient(client, agent)["patient"]["id"]
    ref = _screen(client, agent, pid, engine_ok, "eleve")["referral"]
    spec = login("specialiste@cancerscan.tg")  # spécialiste du CHU démo Lomé
    incoming = client.get(f"{API}/referrals", params={"direction": "incoming"}, headers=spec).json()
    assert [i["id"] for i in incoming] == [ref["id"]]
    assert client.get(f"{API}/patients/{pid}", headers=spec).status_code == 200


def test_facility_services_are_validated(client, login):
    admin = login("admin@cancerscan.tg")
    body = {"code": "X1", "name": "Test", "region": "Kara", "services": ["voyance"]}
    assert client.post(f"{API}/facilities", json=body, headers=admin).status_code == 422
    body |= {"services": ["gynecologie", "gynecologie"], "latitude": 9.5, "longitude": 1.2}
    r = client.post(f"{API}/facilities", json=body, headers=admin)
    assert r.status_code == 201 and r.json()["services"] == ["gynecologie"]
    assert "senologie" in client.get(f"{API}/facilities/services", headers=admin).json()


# --- Corrections issues de la relecture du code ----------------------------------------

def _decide(client, headers, ref_id, **body):
    return client.post(f"{API}/referrals/{ref_id}/decision", json={"final_decision": "Décision du médecin"} | body, headers=headers)


def test_decision_without_referral_removes_access_of_suggested_facility(client, login, engine_ok):
    agent, medecin, spec = login("agent@cancerscan.tg"), login("medecin@cancerscan.tg"), login("specialiste@cancerscan.tg")
    pid = _new_patient(client, agent)["patient"]["id"]
    ref = _screen(client, agent, pid, engine_ok, "eleve")["referral"]
    assert client.get(f"{API}/patients/{pid}", headers=spec).status_code == 200  # proposée : peut se préparer
    assert _decide(client, medecin, ref["id"], final_decision="Surveillance au centre").status_code == 200
    # Plus de référence : la structure seulement suggérée perd l'accès et l'orientation n'est plus « entrante »
    assert client.get(f"{API}/patients/{pid}", headers=spec).status_code == 404
    assert client.get(f"{API}/referrals", params={"direction": "incoming"}, headers=spec).json() == []


def test_suggested_facility_cannot_decide_for_the_referring_doctor(client, login, engine_ok):
    agent, medecin, spec = login("agent@cancerscan.tg"), login("medecin@cancerscan.tg"), login("specialiste@cancerscan.tg")
    pid = _new_patient(client, agent)["patient"]["id"]
    ref = _screen(client, agent, pid, engine_ok, "eleve")["referral"]
    assert _decide(client, spec, ref["id"]).status_code == 403
    assert client.patch(f"{API}/referrals/{ref['id']}/status", json={"status": "annulee"}, headers=spec).status_code == 403
    # Une fois retenue par le médecin, la structure fait avancer le suivi
    r = _decide(client, medecin, ref["id"], to_facility_id=ref["proposed_facility_id"], appointment_date="2026-12-01")
    assert r.status_code == 200
    assert client.patch(f"{API}/referrals/{ref['id']}/status", json={"status": "realisee"}, headers=spec).status_code == 200


def test_agent_notes_locked_after_validation(client, login, engine_ok):
    agent, medecin = login("agent@cancerscan.tg"), login("medecin@cancerscan.tg")
    pid = _new_patient(client, agent)["patient"]["id"]
    s = _screen(client, agent, pid, engine_ok, "eleve")
    notes = {"probabilite_enqueteur": "elevee"}
    assert client.patch(f"{API}/screenings/{s['id']}/agent-notes", json=notes, headers=agent).status_code == 200
    _decide(client, medecin, s["referral"]["id"])
    r = client.patch(f"{API}/screenings/{s['id']}/agent-notes", json={"probabilite_enqueteur": "faible"}, headers=agent)
    assert r.status_code == 409


def test_seed_does_not_restore_services_removed_by_admin():
    from app.seed import seed
    with SessionLocal() as db:
        chu = db.scalar(select(Facility).where(Facility.code == "LOM-CHU"))
        chu.services = []  # mammographe en panne : l'administrateur retire tout
        db.commit()
    seed(demo=True)
    with SessionLocal() as db:
        assert db.scalar(select(Facility).where(Facility.code == "LOM-CHU")).services == []


def test_sync_does_not_report_rolled_back_screenings_as_created(client, login, engine_ok, monkeypatch):
    import uuid
    from app.routers import sync as sync_router
    real, calls = sync_router.create_screening, []

    def flaky(db, user, patient, item):
        calls.append(item)
        if len(calls) == 2:
            raise ValueError("Données invalides")
        return real(db, user, patient, item)

    monkeypatch.setattr(sync_router, "create_screening", flaky)
    h = login("agent@cancerscan.tg")
    s1, s2 = str(uuid.uuid4()), str(uuid.uuid4())
    batch = {"patients": [{"region": "Maritime", "consent_given": True, "client_uuid": str(uuid.uuid4()), "screenings": [
        {"client_uuid": s1, "pathology": "sein", "data": SEIN_COMPLET, "submit": True},
        {"client_uuid": s2, "pathology": "sein", "data": SEIN_COMPLET, "submit": True},
    ]}]}
    out = client.post(f"{API}/sync", json=batch, headers=h).json()
    assert out["patients"][0]["status"] == "error"
    # Le premier dépistage a été annulé avec la patiente : il ne doit pas être annoncé « créé »
    assert out["screenings"] == []
