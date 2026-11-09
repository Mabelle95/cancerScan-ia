import importlib
import math

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from cancerscan_ml import metrics, promote, registry
from cancerscan_ml.features import feature_specs, to_frame
from cancerscan_ml.synthetic import generate
from cancerscan_ml.train import prepare, train


def test_missing_is_distinct_from_negative():
    X = to_frame("sein", [{"masse_presente": False, "modif_peau": "inconnu", "alcool": None}])
    assert X.loc[0, "masse_presente"] == 0.0
    assert math.isnan(X.loc[0, "modif_peau"])
    assert X.loc[0, "alcool"] == "manquant"


def test_only_ml_fields_are_features():
    names = {s.name for s in feature_specs("sein")}
    assert "age" in names and "masse_presente" in names
    assert not {"observations", "masse_cote", "examen_realise", "difficulte_acces"} & names


def test_prepare_excludes_undetermined_and_impossible_values():
    df = pd.DataFrame({"patient_id": ["a", "b", "c"], "target": [1, 0, "indetermine"], "age": [40, 250, 50],
                       "age_premieres_regles": [12, 3, 13]})
    out, report = prepare(df, "sein")
    assert len(out) == 2 and report["exclues_cible_indeterminee"] == 1
    assert report["valeurs_impossibles_mises_a_manquant"] == {"age_premieres_regles": 1, "age": 1}


def test_thresholds_respect_sensitivity_target():
    rng = np.random.default_rng(0)
    y = rng.random(2000) < 0.1
    p = np.clip(y * 0.3 + rng.random(2000) * 0.7, 0, 1)
    t = metrics.choose_thresholds(y.astype(int), p, 0.95, 0.9)
    assert t["eleve"] > t["moyen"]
    assert metrics.at_threshold(y.astype(int), p, t["moyen"])["sensibilite"] >= 0.95


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    models_dir = tmp_path_factory.mktemp("models")
    df = generate("col", 1500, seed=3)
    meta = train(df, "col", external_site="Kara", n_iter=1, data_source="synthetique", models_dir=models_dir)
    return models_dir, meta


def test_training_produces_traceable_unvalidated_model(trained):
    models_dir, meta = trained
    assert meta["validated"] is False and meta["data_source"] == "synthetique"
    assert set(meta["comparison"]) == {"logistic_regression", "random_forest", "xgboost"}
    assert "validation_externe" in meta["evaluation"]
    assert (models_dir / "col" / meta["version"] / "rapport.md").exists()
    assert registry.active_version("col", models_dir) == meta["version"]


def test_synthetic_model_cannot_be_validated(trained):
    models_dir, meta = trained
    with pytest.raises(SystemExit):
        promote.validate("col", meta["version"], "Dr Test", "PV", "aucune", models_dir)


def test_engine_predicts_with_explanations(trained, monkeypatch):
    models_dir, _ = trained
    monkeypatch.setenv("ENGINE_API_KEY", "k")
    monkeypatch.setenv("ENGINE_ALLOW_UNVALIDATED", "true")
    monkeypatch.setattr(registry, "MODELS_DIR", models_dir)
    from cancerscan_ml import engine
    engine = importlib.reload(engine)
    monkeypatch.setattr(registry, "MODELS_DIR", models_dir)
    with TestClient(engine.app) as client:
        body = {"pathology": "col", "features": {"age": 45, "saignement_post_coital": True, "iva_ivl": "positif"}}
        assert client.post("/predict", json=body).status_code == 401
        r = client.post("/predict", json=body, headers={"X-API-Key": "k"})
        assert r.status_code == 200, r.text
        out = r.json()
        assert 0 <= out["score"] <= 1 and out["risk_level"] in ("faible", "moyen", "eleve")
        assert out["explanations"] and out["warnings"]
        # Chaque facteur expliqué porte la réponse saisie (None si non renseignée)
        by_feature = {e["feature"]: e for e in out["explanations"]}
        if "iva_ivl" in by_feature:
            assert by_feature["iva_ivl"]["value"] == "positif"
        assert all("value" in e for e in out["explanations"])
        bad = client.post("/predict", json={"pathology": "col", "features": {"nom": "x"}}, headers={"X-API-Key": "k"})
        assert bad.status_code == 422
        assert client.post("/predict", json={"pathology": "sein", "features": {}}, headers={"X-API-Key": "k"}).status_code == 404


def test_engine_refuses_unvalidated_in_production(trained, monkeypatch):
    models_dir, _ = trained
    monkeypatch.setenv("ENGINE_API_KEY", "k")
    monkeypatch.setenv("ENGINE_ALLOW_UNVALIDATED", "false")
    monkeypatch.setattr(registry, "MODELS_DIR", models_dir)
    from cancerscan_ml import engine
    engine = importlib.reload(engine)
    monkeypatch.setattr(registry, "MODELS_DIR", models_dir)
    with TestClient(engine.app) as client:
        r = client.post("/predict", json={"pathology": "col", "features": {"age": 45}}, headers={"X-API-Key": "k"})
        assert r.status_code == 409


def test_breast_lesions_usg_import_keeps_missing_distinct():
    from cancerscan_ml.datasets.breast_lesions_usg import convert, unmapped_values
    raw = pd.DataFrame({
        "CaseID": [1, 2, 3],
        "Age": [57, "not available", 43],
        "Signs": ["palpable&peau d`orange", "not available", "no"],
        "Symptoms": ["nipple discharge&family history of breast/ovarian cancer", "no", "not available"],
        "Classification": ["malignant", "benign", "normal"],
        "Verification": ["confirmed by biopsy"] * 3,
    })
    out = convert(raw)
    assert out["target"].tolist() == [1, 0, 0]
    assert out.loc[0, "masse_presente"] and out.loc[0, "modif_peau"] and out.loc[0, "ecoulement"] == "non_precise"
    assert pd.isna(out.loc[1, "masse_presente"]) and pd.isna(out.loc[1, "age"])   # inconnu reste inconnu
    assert out.loc[2, "masse_presente"] == False and pd.isna(out.loc[2, "atcd_familial_sein_ovaire"])  # noqa: E712
    assert unmapped_values(raw) == {"Signs": set(), "Symptoms": set()}


def _adversarial_sein(n=900, seed=0):
    """Données piégées : l'antécédent familial est associé à MOINS de cancers (comme le biais de BrEaST)."""
    rng = np.random.default_rng(seed)
    fam = rng.random(n) < 0.3
    mass = rng.random(n) < 0.3
    logit = -1.0 + 2.0 * mass - 1.5 * fam
    y = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    records = [{"age": float(a), "atcd_familial_sein_ovaire": bool(f), "masse_presente": bool(m), "modif_peau": False,
                "retraction_mamelon": False} for a, f, m in zip(rng.integers(30, 70, n), fam, mass)]
    return to_frame("sein", records), y


@pytest.mark.parametrize("algo", ["logistic_regression", "random_forest", "xgboost"])
def test_monotone_constraint_overrides_biased_data(algo):
    from cancerscan_ml.train import candidates
    X, y = _adversarial_sein()
    pipe, _ = candidates("sein", pos_weight=2.0, seed=0, missing_indicators=False, monotone=True)[algo]
    if algo != "logistic_regression":
        pipe.set_params(clf__base__n_estimators=60)
    pipe.fit(X, y)
    with_fam = X.assign(atcd_familial_sein_ovaire=1.0)
    without = X.assign(atcd_familial_sein_ovaire=0.0)
    diff = pipe.predict_proba(with_fam)[:, 1] - pipe.predict_proba(without)[:, 1]
    assert diff.min() >= -1e-9  # avoir un antécédent familial ne fait JAMAIS baisser le risque


def test_unconstrained_model_does_learn_the_bias():
    """Contrôle : sans contrainte, le modèle apprend bien l'effet inverse — la contrainte est donc utile."""
    from cancerscan_ml.train import candidates
    X, y = _adversarial_sein()
    pipe, _ = candidates("sein", pos_weight=2.0, seed=0, missing_indicators=False, monotone=False)["logistic_regression"]
    pipe.fit(X, y)
    names = list(pipe.named_steps["pre"].get_feature_names_out())
    assert pipe.named_steps["clf"].coef_[0][names.index("atcd_familial_sein_ovaire")] < 0


def test_constrained_lr_matches_sklearn_when_unconstrained():
    from sklearn.linear_model import LogisticRegression
    from cancerscan_ml.monotone import ConstrainedLogisticRegression
    rng = np.random.default_rng(1)
    X = rng.normal(size=(400, 4))
    y = (X @ np.array([1.0, -0.5, 0.0, 2.0]) + rng.normal(size=400) > 0).astype(int)
    ours = ConstrainedLogisticRegression(C=1.0).fit(X, y)
    ref = LogisticRegression(C=1.0).fit(X, y)
    assert np.allclose(ours.coef_, ref.coef_, atol=1e-3) and np.allclose(ours.intercept_, ref.intercept_, atol=1e-3)
    constrained = ConstrainedLogisticRegression(C=1.0, leading_constraints=(0, 1)).fit(X, y)
    assert constrained.coef_[0][1] >= 0  # coefficient naturellement négatif, forcé à ≥ 0


def test_explanations_skip_unanswered_factors(trained):
    models_dir, meta = trained
    model = registry.load("col", models_dir=models_dir)
    out = registry.predict(model, {"age": 45, "saignement_post_coital": True, "atcd_hpv": "inconnu", "tabac": None})
    shown = {e["feature"] for e in out["explanations"]}
    assert "atcd_hpv" not in shown and "tabac" not in shown  # réponses manquantes : jamais présentées comme facteur
    assert shown  # les facteurs renseignés restent expliqués
