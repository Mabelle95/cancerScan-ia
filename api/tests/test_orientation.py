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
