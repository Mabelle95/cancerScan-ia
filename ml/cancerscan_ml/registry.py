"""Stockage versionné des modèles et inférence avec explications.

Arborescence :
    models/<pathologie>/<version>/model.joblib   pipeline calibré + modèle d'explication
    models/<pathologie>/<version>/metadata.json  seuils, métriques, statut de validation, provenance des données
    models/<pathologie>/ACTIVE                    version déployée
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np

from cancerscan_ml.features import feature_specs, source_feature, to_frame

MODELS_DIR = Path(os.environ.get("MODELS_DIR", Path(__file__).resolve().parents[1] / "models"))


@dataclass
class LoadedModel:
    metadata: dict
    calibrated: object      # pipeline complet, probabilités calibrées
    explainer_model: object  # pipeline non calibré utilisé pour les contributions (SHAP)

    @property
    def pathology(self) -> str:
        return self.metadata["pathology"]


def save(artifact: dict, metadata: dict, models_dir: Path | None = None, activate: bool = True) -> Path:
    models_dir = models_dir or MODELS_DIR
    target = models_dir / metadata["pathology"] / metadata["version"]
    target.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, target / "model.joblib")
    (target / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    if activate:
        (models_dir / metadata["pathology"] / "ACTIVE").write_text(metadata["version"], encoding="utf-8")
    return target


def read_metadata(pathology: str, version: str, models_dir: Path | None = None) -> dict:
    models_dir = models_dir or MODELS_DIR
    return json.loads((models_dir / pathology / version / "metadata.json").read_text(encoding="utf-8"))


def write_metadata(metadata: dict, models_dir: Path | None = None) -> None:
    models_dir = models_dir or MODELS_DIR
    path = models_dir / metadata["pathology"] / metadata["version"] / "metadata.json"
    path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")


def active_version(pathology: str, models_dir: Path | None = None) -> str | None:
    models_dir = models_dir or MODELS_DIR
    marker = models_dir / pathology / "ACTIVE"
    return marker.read_text(encoding="utf-8").strip() if marker.exists() else None


def load(pathology: str, version: str | None = None, models_dir: Path | None = None) -> LoadedModel | None:
    models_dir = models_dir or MODELS_DIR
    version = version or active_version(pathology, models_dir)
    if not version:
        return None
    artifact = joblib.load(models_dir / pathology / version / "model.joblib")
    return LoadedModel(read_metadata(pathology, version, models_dir), artifact["calibrated"], artifact["explainer_model"])


def classify(score: float, thresholds: dict) -> str:
    if score >= thresholds["eleve"]:
        return "eleve"
    if score >= thresholds["moyen"]:
        return "moyen"
    return "faible"


def explain(model: LoadedModel, X, top: int = 5, raw: dict | None = None) -> list[dict]:
    """Contributions par variable d'origine (valeurs SHAP du modèle non calibré : échelle log-odds pour la
    régression logistique et XGBoost, échelle de probabilité pour Random Forest). Seuls le signe et l'ordre
    sont à interpréter.

    Elles indiquent ce qui a pesé dans l'estimation ; ce ne sont pas des preuves de causalité.
    """
    pre = model.explainer_model.named_steps["pre"]
    clf = model.explainer_model.named_steps["clf"]
    clf = getattr(clf, "estimator_", clf)  # modèles d'arbres sous contrainte de monotonie : estimateur interne
    Xt = pre.transform(X)
    names = pre.get_feature_names_out()
    algo = model.metadata["algorithm"]

    if algo == "logistic_regression":
        background = np.asarray(model.metadata["explain_background"])
        contrib = clf.coef_[0] * (Xt[0] - background)
    elif algo == "xgboost":
        import xgboost as xgb
        contrib = clf.get_booster().predict(xgb.DMatrix(Xt), pred_contribs=True)[0][:-1]
    else:
        import shap
        values = shap.TreeExplainer(clf).shap_values(Xt)
        values = values[1] if isinstance(values, list) else values
        contrib = values[0][:, 1] if np.ndim(values[0]) == 2 else values[0]

    pathology = model.pathology
    by_feature: dict[str, float] = {}
    for name, c in zip(names, contrib):
        src = source_feature(name, pathology)
        by_feature[src] = by_feature.get(src, 0.0) + float(c)
    labels = {s.name: s.label for s in feature_specs(pathology)}
    if raw is not None:
        # Une réponse non renseignée n'est pas un « facteur » : l'afficher (« non renseigné → diminue ») rassurerait à tort.
        by_feature = {f: c for f, c in by_feature.items() if raw.get(f) not in (None, "", "inconnu")}
    ranked = sorted(by_feature.items(), key=lambda kv: abs(kv[1]), reverse=True)
    return [
        # « value » : la réponse saisie, affichée à côté du facteur pour qu'une contribution ne soit jamais
        # lue sans son contexte (ex. « Antécédent familial : Non » qui augmente l'estimation = artefact du modèle).
        {"feature": f, "label": labels.get(f, f), "value": (raw or {}).get(f), "contribution": round(c, 4),
         "direction": "augmente" if c > 0 else "diminue"}
        for f, c in ranked[:top] if abs(c) > 1e-6
    ]


def predict(model: LoadedModel, features: dict) -> dict:
    X = to_frame(model.pathology, [features])
    score = float(model.calibrated.predict_proba(X)[0, 1])
    meta = model.metadata
    return {
        "model_id": meta["model_id"],
        "model_version": meta["version"],
        "pathology": meta["pathology"],
        "algorithm": meta["algorithm"],
        "validated": meta.get("validated", False),
        "data_source": meta.get("data_source"),
        "score": round(score, 4),
        "risk_level": classify(score, meta["thresholds"]),
        "thresholds": meta["thresholds"],
        "explanations": explain(model, X, raw=features),
        "missing_features": [k for k, v in features.items() if v is None or v == "inconnu"],
    }
