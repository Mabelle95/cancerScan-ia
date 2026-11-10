import uuid

from sqlalchemy import select, text

from app.db import SessionLocal
from app.models import AuditLog

API = "/api/v1"

SEIN_COMPLET = {
    "atcd_familial_sein_ovaire": False,
    "atcd_personnel_sein": False,
    "masse_presente": False,
    "modif_peau": False,
    "retraction_mamelon": False,
    "examen_realise": True,
    "nb_grossesses_terme": 2,
    "age_premiere_grossesse": 22,
    "probabilite_enqueteur": "faible",
}

PATIENTE = {"full_name": "Afi Mensah", "phone": "+228 90 00 00 01", "birth_date": "1975-03-10",
            "region": "Maritime", "locality": "Bè", "consent_given": True}


def _new_patient(client, headers, **overrides):
    r = client.post(f"{API}/patients", json=PATIENTE | overrides, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


# --- Authentification et permissions ---------------------------------------------------

def test_login_rejects_bad_password(client):
    r = client.post(f"{API}/auth/login", json={"email": "agent@cancerscan.tg", "password": "wrong-password"})
    assert r.status_code == 401


def test_requires_token(client):
    assert client.get(f"{API}/patients").status_code == 401


def test_admin_cannot_read_medical_records(client, login):
    assert client.get(f"{API}/patients", headers=login("admin@cancerscan.tg")).status_code == 403


def test_responsable_only_sees_stats(client, login):
    h = login("responsable@cancerscan.tg")
    assert client.get(f"{API}/patients", headers=h).status_code == 403
    assert client.get(f"{API}/stats/overview", headers=h).status_code == 200


# --- Patientes ----------------------------------------------------------------------

def test_consent_required(client, login):
    r = client.post(f"{API}/patients", json=PATIENTE | {"consent_given": False}, headers=login("agent@cancerscan.tg"))
    assert r.status_code == 422


def test_identifying_data_encrypted_at_rest(client, login):
    p = _new_patient(client, login("agent@cancerscan.tg"))
    assert p["patient"]["full_name"] == "Afi Mensah"
    with SessionLocal() as db:
        raw = db.execute(text("SELECT full_name, phone FROM patients")).one()
    assert "Afi" not in raw[0] and "90 00 00 01" not in raw[1] and "90000001" not in raw[1]


def test_duplicate_detection_by_phone_and_search(client, login):
    h = login("agent@cancerscan.tg")
    first = _new_patient(client, h)
    second = _new_patient(client, h, full_name="Autre Nom")
    assert [d["id"] for d in second["possible_duplicates"]] == [first["patient"]["id"]]
    assert len(client.get(f"{API}/patients", params={"q": "mensah"}, headers=h).json()) == 1
    assert len(client.get(f"{API}/patients", params={"q": "90000001"}, headers=h).json()) == 2


def test_other_facility_cannot_access(client, login):
    p = _new_patient(client, login("agent@cancerscan.tg"))
    # Le spécialiste du CHU n'a pas accès tant que la patiente ne lui est pas référée
    r = client.get(f"{API}/patients/{p['patient']['id']}", headers=login("specialiste@cancerscan.tg"))
    assert r.status_code == 404


# --- Dépistage, IA et orientation -----------------------------------------------------

def test_incomplete_form_stays_draft(client, login, engine_ok):
    h = login("agent@cancerscan.tg")
    pid = _new_patient(client, h)["patient"]["id"]
    r = client.post(f"{API}/patients/{pid}/screenings", json={"pathology": "sein", "data": {"masse_presente": True}, "submit": True}, headers=h)
    body = r.json()
    assert body["screening"]["status"] == "brouillon"
    assert "modif_peau" in body["missing_required"]
    assert engine_ok.calls == []


def test_invalid_values_rejected(client, login, engine_ok):
    h = login("agent@cancerscan.tg")
    pid = _new_patient(client, h)["patient"]["id"]
    data = SEIN_COMPLET | {"age_premieres_regles": 3, "alcool": "beaucoup"}
    body = client.post(f"{API}/patients/{pid}/screenings", json={"pathology": "sein", "data": data, "submit": True}, headers=h).json()
    assert set(body["errors"]) == {"age_premieres_regles", "alcool"}
    assert body["screening"]["status"] == "brouillon"


def test_full_workflow_with_ai(client, login, engine_ok):
    agent, medecin = login("agent@cancerscan.tg"), login("medecin@cancerscan.tg")
    pid = _new_patient(client, agent)["patient"]["id"]
    engine_ok.level, engine_ok.score = "eleve", 0.81
    r = client.post(f"{API}/patients/{pid}/screenings", json={"pathology": "sein", "data": SEIN_COMPLET | {"masse_presente": True, "masse_cote": "gauche"}, "submit": True}, headers=agent)
    s = r.json()["screening"]
    assert s["status"] == "analyse"
    assert s["assessments"][0]["risk_level"] == "eleve"
    assert s["referral"]["proposed_level"] == "eleve"
    assert "Référence prioritaire" in s["referral"]["proposed_recommendation"]

    # Seules les variables `ml` + l'âge sont transmises — jamais le nom ni le téléphone ni les champs non ML
    _, features = engine_ok.calls[0]
    assert features["age"] >= 49 and "full_name" not in features and "phone" not in features
    assert "masse_cote" not in features and "observations" not in features
    # L'appréciation de l'enquêteur est conservée mais jamais transmise au modèle
    assert "probabilite_enqueteur" not in features

    # L'agent ne peut pas valider l'orientation ; le médecin oui
    ref_id = s["referral"]["id"]
    chu = next(f for f in client.get(f"{API}/facilities", headers=agent).json() if f["code"] == "LOM-CHU")
    decision = {"final_decision": "Référence au CHU pour échographie", "to_facility_id": chu["id"], "appointment_date": "2026-12-01"}
    assert client.post(f"{API}/referrals/{ref_id}/decision", json=decision, headers=agent).status_code == 403
    r = client.post(f"{API}/referrals/{ref_id}/decision", json=decision, headers=medecin)
    assert r.status_code == 200 and r.json()["status"] == "programmee"

    # Le spécialiste du CHU accède désormais au dossier référé et peut renseigner les examens
    spec = login("specialiste@cancerscan.tg")
    assert client.get(f"{API}/patients/{pid}", headers=spec).status_code == 200
    incoming = client.get(f"{API}/referrals", params={"direction": "incoming"}, headers=spec).json()
    assert [i["id"] for i in incoming] == [ref_id]
    exam = {"screening_id": s["id"], "exam_type": "echographie_mammaire", "result": "Nodule ACR 3", "conclusion": "benin"}
    assert client.post(f"{API}/patients/{pid}/exams", json=exam, headers=spec).status_code == 201
    r = client.patch(f"{API}/referrals/{ref_id}/status", json={"status": "realisee"}, headers=spec)
    assert r.json()["status"] == "realisee"

    with SessionLocal() as db:
        actions = set(db.scalars(select(AuditLog.action)))
    assert {"login", "create", "ai_run", "decide", "status_change"} <= actions


def test_alert_sign_escalates_low_model_score(client, login, engine_ok):
    """Un résultat faible ne doit jamais masquer un signe d'alerte (cahier des charges §4.4)."""
    h = login("agent@cancerscan.tg")
    pid = _new_patient(client, h)["patient"]["id"]
    engine_ok.level = "faible"
    data = SEIN_COMPLET | {"retraction_mamelon": True}
    s = client.post(f"{API}/patients/{pid}/screenings", json={"pathology": "sein", "data": data, "submit": True}, headers=h).json()["screening"]
    assert s["assessments"][0]["risk_level"] == "faible"
    assert s["alerts"][0]["field"] == "retraction_mamelon"
    assert s["referral"]["proposed_level"] == "moyen"
    assert "évaluation médicale est nécessaire" in s["referral"]["proposed_recommendation"]


def test_engine_down_defers_analysis_then_processes(client, login, engine_down, engine_ok, monkeypatch):
    from app.services import engine_client

    h = login("agent@cancerscan.tg")
    pid = _new_patient(client, h)["patient"]["id"]
    monkeypatch.setattr(engine_client, "predict", lambda p, f: (_ for _ in ()).throw(engine_client.EngineUnavailable("down")))
    r = client.post(f"{API}/patients/{pid}/screenings", json={"pathology": "sein", "data": SEIN_COMPLET, "submit": True}, headers=h).json()
    assert r["ai_pending"] is True and r["screening"]["status"] == "soumis"
    assert r["screening"]["assessments"] == []

    monkeypatch.setattr(engine_client, "predict", engine_ok)
    assert client.post(f"{API}/screenings/process-pending", headers=h).json() == {"pending": 1, "analysed": 1}
    s = client.get(f"{API}/screenings/{r['screening']['id']}", headers=h).json()
    assert s["status"] == "analyse"


def test_hidden_fields_are_ignored(client, login, engine_ok):
    h = login("agent@cancerscan.tg")
    pid = _new_patient(client, h)["patient"]["id"]
    # age_premiere_grossesse n'est affiché que si nb_grossesses_terme > 0
    data = SEIN_COMPLET | {"nb_grossesses_terme": 0, "age_premiere_grossesse": 25}
    client.post(f"{API}/patients/{pid}/screenings", json={"pathology": "sein", "data": data, "submit": True}, headers=h)
    _, features = engine_ok.calls[0]
    assert features["age_premiere_grossesse"] is None


# --- Synchronisation hors ligne --------------------------------------------------------

def test_offline_sync_is_idempotent(client, login, engine_ok):
    h = login("agent@cancerscan.tg")
    pu, su = str(uuid.uuid4()), str(uuid.uuid4())
    batch = {"patients": [PATIENTE | {"client_uuid": pu, "screenings": [
        {"client_uuid": su, "pathology": "col", "submit": True, "data": {
            "atcd_hpv": "inconnu", "depistage_col_anterieur": "jamais", "saignement_anormal": False, "saignement_post_coital": True}}]}]}
    first = client.post(f"{API}/sync", json=batch, headers=h).json()
    assert first["patients"][0]["status"] == "created" and first["screenings"][0]["status"] == "created"
    second = client.post(f"{API}/sync", json=batch, headers=h).json()
    assert second["patients"][0]["status"] == "already_synced"
    assert second["screenings"][0]["server_id"] == first["screenings"][0]["server_id"]
    assert len(engine_ok.calls) == 1


def test_sync_reports_errors_per_item(client, login):
    h = login("agent@cancerscan.tg")
    batch = {"screenings": [{"client_uuid": str(uuid.uuid4()), "patient_id": str(uuid.uuid4()), "pathology": "sein", "data": {}}]}
    out = client.post(f"{API}/sync", json=batch, headers=h).json()
    assert out["screenings"][0]["status"] == "error"


# --- Statistiques ----------------------------------------------------------------------

def test_stats_mask_small_cells(client, login, engine_ok):
    h = login("agent@cancerscan.tg")
    for i in range(6):
        pid = _new_patient(client, h, phone=f"+228 90 00 00 {i:02d}", region="Maritime" if i < 5 else "Kara")["patient"]["id"]
        client.post(f"{API}/patients/{pid}/screenings", json={"pathology": "sein", "data": SEIN_COMPLET, "submit": True}, headers=h)
    stats = client.get(f"{API}/stats/overview", headers=login("responsable@cancerscan.tg")).json()
    assert stats["totals"]["depistages"] == 6
    assert stats["par_region"] == {"Maritime": 5, "Kara": None}
    assert stats["par_niveau_risque"] == {"faible": 6}


def test_agent_opinion_is_given_after_the_ai_result(client, login, engine_ok, engine_down, monkeypatch):
    from app.services import engine_client

    h = login("agent@cancerscan.tg")
    pid = _new_patient(client, h)["patient"]["id"]
    data = {k: v for k, v in SEIN_COMPLET.items() if k != "probabilite_enqueteur"}  # plus demandée avant l'analyse
    # Sans résultat IA (moteur indisponible), l'appréciation est refusée
    monkeypatch.setattr(engine_client, "predict", lambda p, f: (_ for _ in ()).throw(engine_client.EngineUnavailable("down")))
    s = client.post(f"{API}/patients/{pid}/screenings", json={"pathology": "sein", "data": data, "submit": True}, headers=h).json()["screening"]
    assert s["status"] == "soumis"
    assert client.patch(f"{API}/screenings/{s['id']}/agent-notes", json={"probabilite_enqueteur": "faible"}, headers=h).status_code == 409

    monkeypatch.setattr(engine_client, "predict", engine_ok)
    client.post(f"{API}/screenings/process-pending", headers=h)
    r = client.patch(f"{API}/screenings/{s['id']}/agent-notes", headers=h,
                     json={"probabilite_enqueteur": "elevee", "conseils_donnes": "Consultation au CHU"})
    assert r.status_code == 200
    out = r.json()
    assert out["data"]["probabilite_enqueteur"] == "elevee" and out["data"]["conseils_donnes"] == "Consultation au CHU"
    assert len(out["assessments"]) == 1  # l'appréciation ne relance pas l'analyse IA
    # Seules les questions « après résultat » sont modifiables par cette voie
    bad = client.patch(f"{API}/screenings/{s['id']}/agent-notes", json={"masse_presente": True}, headers=h)
    assert bad.status_code == 422
