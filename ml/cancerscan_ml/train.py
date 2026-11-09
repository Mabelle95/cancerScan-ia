"""Entraînement, comparaison, calibration et évaluation des modèles d'une pathologie.

Usage :
    python -m cancerscan_ml.train --pathology sein --data data/sein.csv [--external-site Kara]

Le fichier CSV contient une ligne par dépistage avec :
- `patient_id` (pseudonymisé) : la séparation des jeux se fait par patiente ;
- `target` : 1 = résultat de référence positif (cancer / lésion selon la définition validée), 0 = négatif
  après évaluation appropriée ; toute autre valeur (indéterminé, non disponible) est EXCLUE et comptée ;
- `site` (optionnel) : établissement ou région, pour la validation externe et l'analyse par sous-groupe ;
- les variables `ml` du formulaire de la pathologie, et `age`.
"""

import argparse
import json
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import loguniform, randint, uniform
from sklearn.base import clone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupShuffleSplit, RandomizedSearchCV, StratifiedGroupKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from xgboost import XGBClassifier

from cancerscan_ml import metrics, registry
from cancerscan_ml.features import (
    feature_specs, form_version, leading_constraints, load_form, monotone_features, preprocessor, to_frame,
)
from cancerscan_ml.monotone import ConstrainedLogisticRegression, MonotoneTreeClassifier

warnings.filterwarnings("ignore", category=UserWarning)

AGE_BRACKETS = [0, 30, 40, 50, 60, 70, 200]
AGE_LABELS = ["<30", "30-39", "40-49", "50-59", "60-69", "70+"]


# --- Préparation des données (CRISP-DM étape 3) -------------------------------------------

def prepare(df: pd.DataFrame, pathology: str) -> tuple[pd.DataFrame, dict]:
    report = {"lignes_initiales": len(df)}
    for col in ("patient_id", "target"):
        if col not in df.columns:
            raise ValueError(f"Colonne obligatoire absente : {col}")
    df = df.copy()
    df["target"] = pd.to_numeric(df["target"], errors="coerce")
    undetermined = ~df["target"].isin([0, 1])
    report["exclues_cible_indeterminee"] = int(undetermined.sum())
    df = df[~undetermined]
    before = len(df)
    df = df.drop_duplicates()
    report["doublons_supprimes"] = before - len(df)

    names = [s.name for s in feature_specs(pathology)]
    absent = [n for n in names if n not in df.columns]
    if absent:
        report["variables_absentes"] = absent
    # Valeurs impossibles : bornes du formulaire → manquant
    impossible = {}
    for section in load_form(pathology)["sections"]:
        for f in section["fields"]:
            if f.get("ml") and f["type"] in ("integer", "number") and f["id"] in df.columns:
                col = pd.to_numeric(df[f["id"]], errors="coerce")
                bad = (col < f.get("min", -np.inf)) | (col > f.get("max", np.inf))
                if bad.any():
                    impossible[f["id"]] = int(bad.sum())
                    df.loc[bad, f["id"]] = np.nan
    if "age" in df.columns:
        bad = (pd.to_numeric(df["age"], errors="coerce") < 10) | (pd.to_numeric(df["age"], errors="coerce") > 110)
        if bad.any():
            impossible["age"] = int(bad.sum())
            df.loc[bad, "age"] = np.nan
    report["valeurs_impossibles_mises_a_manquant"] = impossible

    report.update({
        "lignes_retenues": len(df), "patientes": int(df["patient_id"].nunique()),
        "positifs": int(df["target"].sum()), "prevalence": round(float(df["target"].mean()), 4),
        "taux_manquant": {n: round(float(df[n].isna().mean()), 3) for n in names if n in df.columns},
    })
    return df.reset_index(drop=True), report


def to_X(df: pd.DataFrame, pathology: str) -> pd.DataFrame:
    records = df.replace({np.nan: None}).to_dict("records")
    return to_frame(pathology, records)


# --- Modèles candidats (CRISP-DM étape 4) -------------------------------------------------

def candidates(pathology: str, pos_weight: float, seed: int, missing_indicators: bool = True, monotone: bool = True) -> dict:
    """Modèles candidats. Avec `monotone`, les facteurs déclarés « increasing » dans le formulaire ne peuvent
    qu'augmenter le risque (voir cancerscan_ml.monotone)."""
    cst = leading_constraints(pathology) if monotone else ()
    pre = lambda scale: preprocessor(pathology, scale=scale, missing_indicators=missing_indicators)  # noqa: E731
    rf = RandomForestClassifier(class_weight="balanced_subsample", n_jobs=-1, random_state=seed)
    xgb = XGBClassifier(scale_pos_weight=pos_weight, eval_metric="logloss", n_jobs=-1, random_state=seed)
    return {
        "logistic_regression": (
            Pipeline([("pre", pre(True)), ("clf", ConstrainedLogisticRegression(class_weight="balanced", leading_constraints=cst))]),
            {"clf__C": loguniform(1e-3, 10)},
        ),
        "random_forest": (
            Pipeline([("pre", pre(False)), ("clf", MonotoneTreeClassifier(rf, leading_constraints=cst))]),
            {"clf__base__n_estimators": randint(200, 600), "clf__base__max_depth": [3, 5, 8, None],
             "clf__base__min_samples_leaf": randint(2, 30), "clf__base__max_features": ["sqrt", 0.5]},
        ),
        "xgboost": (
            Pipeline([("pre", pre(False)), ("clf", MonotoneTreeClassifier(xgb, leading_constraints=cst))]),
            {"clf__base__n_estimators": randint(100, 500), "clf__base__max_depth": randint(2, 6),
             "clf__base__learning_rate": loguniform(0.01, 0.3), "clf__base__subsample": uniform(0.6, 0.4),
             "clf__base__colsample_bytree": uniform(0.5, 0.5), "clf__base__reg_lambda": loguniform(0.1, 10)},
        ),
    }


def train(df: pd.DataFrame, pathology: str, *, external_site: str | None = None, target_sensitivity: float = 0.95,
          target_specificity: float = 0.90, n_iter: int = 15, seed: int = 42, data_source: str = "inconnue",
          models_dir: Path | None = None, activate: bool = True, missing_indicators: bool = True,
          monotone: bool = True) -> dict:
    df, data_report = prepare(df, pathology)

    external = None
    if external_site:
        if "site" not in df.columns:
            raise ValueError("--external-site nécessite une colonne `site`")
        external = df[df["site"] == external_site]
        df = df[df["site"] != external_site]

    # Séparation au niveau des patientes : une même patiente n'apparaît que dans un seul jeu.
    train_idx, test_idx = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=seed).split(df, groups=df["patient_id"]))
    tr, te = df.iloc[train_idx], df.iloc[test_idx]
    X_tr, y_tr, g_tr = to_X(tr, pathology), tr["target"].to_numpy(int), tr["patient_id"].to_numpy()
    X_te, y_te = to_X(te, pathology), te["target"].to_numpy(int)
    if y_tr.sum() < 10:
        raise ValueError(f"Seulement {y_tr.sum()} cas positifs en apprentissage : effectif insuffisant pour entraîner un modèle.")

    cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=seed)
    splits = list(cv.split(X_tr, y_tr, g_tr))
    pos_weight = float((y_tr == 0).sum() / max(y_tr.sum(), 1))
    scoring = {"pr_auc": "average_precision", "roc_auc": "roc_auc", "brier": "neg_brier_score"}

    comparison, searches = {}, {}
    for name, (pipe, params) in candidates(pathology, pos_weight, seed, missing_indicators, monotone).items():
        search = RandomizedSearchCV(pipe, params, n_iter=n_iter, scoring=scoring, refit="pr_auc", cv=splits,
                                    random_state=seed, n_jobs=1)
        search.fit(X_tr, y_tr)
        i = search.best_index_
        res = search.cv_results_
        comparison[name] = {
            "pr_auc_cv": round(float(res["mean_test_pr_auc"][i]), 4), "pr_auc_cv_std": round(float(res["std_test_pr_auc"][i]), 4),
            "roc_auc_cv": round(float(res["mean_test_roc_auc"][i]), 4), "brier_cv": round(float(-res["mean_test_brier"][i]), 4),
            "hyperparametres": {k.replace("clf__base__", "").replace("clf__", ""): (v.item() if hasattr(v, "item") else v)
                                for k, v in search.best_params_.items()},
        }
        searches[name] = search
        print(f"  {name:<20} PR-AUC={comparison[name]['pr_auc_cv']:.3f}  ROC-AUC={comparison[name]['roc_auc_cv']:.3f}")

    # Sélection : meilleure PR-AUC ; la régression logistique (plus interprétable) est préférée si l'écart est < 0,01.
    best = max(comparison, key=lambda n: comparison[n]["pr_auc_cv"])
    if best != "logistic_regression" and comparison[best]["pr_auc_cv"] - comparison["logistic_regression"]["pr_auc_cv"] < 0.01:
        best = "logistic_regression"
    base = searches[best].best_estimator_

    # Calibration des probabilités (CRISP-DM étape 5)
    method = "isotonic" if y_tr.sum() >= 200 else "sigmoid"
    calibrated = CalibratedClassifierCV(clone(base), method=method, cv=splits).fit(X_tr, y_tr)

    # Seuils déterminés sur des prédictions hors échantillon (jamais sur le jeu de test)
    oof = cross_val_predict(CalibratedClassifierCV(clone(base), method=method, cv=3), X_tr, y_tr, groups=g_tr, cv=cv,
                            method="predict_proba")[:, 1]
    thresholds = metrics.choose_thresholds(y_tr, oof, target_sensitivity, target_specificity)

    p_te = calibrated.predict_proba(X_te)[:, 1]
    evaluation = {"validation_croisee_hors_echantillon": metrics.evaluate(y_tr, oof, thresholds),
                  "test": metrics.evaluate(y_te, p_te, thresholds)}
    age_groups = (pd.cut(pd.to_numeric(te["age"], errors="coerce"), AGE_BRACKETS, labels=AGE_LABELS, right=False)
                  .cat.add_categories("inconnu").fillna("inconnu").astype(str).to_numpy())
    evaluation["sous_groupes_test"] = {"tranche_age": metrics.subgroups(y_te, p_te, age_groups, thresholds)}
    if "site" in te.columns:
        evaluation["sous_groupes_test"]["site"] = metrics.subgroups(y_te, p_te, te["site"], thresholds)
    if external is not None and len(external):
        p_ext = calibrated.predict_proba(to_X(external, pathology))[:, 1]
        evaluation["validation_externe"] = {"site": external_site, **metrics.evaluate(external["target"].to_numpy(int), p_ext, thresholds)}

    now = datetime.now(timezone.utc)
    version = now.strftime("%Y%m%d-%H%M%S")
    pre = base.named_steps["pre"]
    metadata = {
        "model_id": f"{pathology}-{best}",
        "pathology": pathology,
        "version": version,
        "algorithm": best,
        "form_version": form_version(pathology),
        "features": [s.name for s in feature_specs(pathology)],
        "trained_at": now.isoformat(),
        "data_source": data_source,
        "data_report": data_report,
        "split": {"methode": "par patiente (GroupShuffleSplit 80/20) + StratifiedGroupKFold 5 plis",
                  "apprentissage": int(len(tr)), "test": int(len(te)), "externe": int(len(external)) if external is not None else 0},
        "calibration": method,
        "missing_indicators": missing_indicators,
        "monotone_constraints": monotone_features(pathology) if monotone else {},
        "threshold_policy": {"sensibilite_cible_moyen": target_sensitivity, "specificite_cible_eleve": target_specificity},
        "thresholds": thresholds,
        "comparison": comparison,
        "evaluation": evaluation,
        "validated": False,
        "validation": None,
        "explain_background": pre.transform(X_tr).mean(axis=0).tolist() if best == "logistic_regression" else None,
    }
    path = registry.save({"calibrated": calibrated, "explainer_model": base}, metadata, models_dir, activate=activate)
    (path / "rapport.md").write_text(render_report(metadata), encoding="utf-8")
    print(f"Modèle retenu : {best} — enregistré dans {path}")
    return metadata


# --- Rapport -----------------------------------------------------------------------------

def _fmt(v):
    return "—" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))


def render_report(m: dict) -> str:
    t = m["evaluation"]["test"]
    lines = [
        f"# Rapport de performance — {m['model_id']} v{m['version']}",
        "",
        f"> **Statut : {'VALIDÉ' if m['validated'] else 'NON VALIDÉ — usage clinique interdit'}** · "
        f"source des données : **{m['data_source']}** · formulaire v{m['form_version']}",
        "",
        "## Données",
        "",
        "| Indicateur | Valeur |", "|---|---|",
        *[f"| {k} | {_fmt(v)} |" for k, v in m["data_report"].items() if not isinstance(v, (dict, list))],
        "",
        "## Comparaison des modèles (validation croisée par patiente, 5 plis)",
        "",
        "| Modèle | PR-AUC | ROC-AUC | Brier |", "|---|---|---|---|",
        *[f"| {n}{' **(retenu)**' if n == m['algorithm'] else ''} | {c['pr_auc_cv']:.3f} ± {c['pr_auc_cv_std']:.3f} | "
          f"{c['roc_auc_cv']:.3f} | {c['brier_cv']:.3f} |" for n, c in m["comparison"].items()],
        "",
        f"## Seuils proposés (calibration {m['calibration']})",
        "",
        f"- **Moyen** ≥ {m['thresholds']['moyen']} (sensibilité cible {m['threshold_policy']['sensibilite_cible_moyen']:.0%})",
        f"- **Élevé** ≥ {m['thresholds']['eleve']} (spécificité cible {m['threshold_policy']['specificite_cible_eleve']:.0%})",
        "",
        "Ces seuils sont une proposition statistique : ils doivent être arrêtés avec les professionnels de santé "
        "en tenant compte des conséquences cliniques des faux négatifs et des faux positifs.",
        "",
        f"## Jeu de test (n = {t['n']}, positifs = {t['positifs']})",
        "",
        f"ROC-AUC {_fmt(t['roc_auc'])} · PR-AUC {_fmt(t['pr_auc'])} · Brier {_fmt(t['brier'])}",
        "",
        "| Orientation | Sensibilité | Spécificité | VPP | VPN | Faux négatifs |", "|---|---|---|---|---|---|",
        *[f"| {lbl} | {_fmt(t[k]['sensibilite'])} | {_fmt(t[k]['specificite'])} | {_fmt(t[k]['vpp'])} | {_fmt(t[k]['vpn'])} | {t[k]['fn']} |"
          for lbl, k in (("Moyen ou élevé", "orientation_moyen_ou_plus"), ("Élevé", "orientation_eleve"))],
        "",
        "## Performance par sous-groupe (test)",
        "",
    ]
    for dim, groups in m["evaluation"]["sous_groupes_test"].items():
        lines += [f"**{dim}**", "", "| Groupe | n | Positifs | ROC-AUC | Sensibilité | Spécificité |", "|---|---|---|---|---|---|"]
        lines += [f"| {g} | {v['n']} | {v['positifs']} | {_fmt(v.get('roc_auc'))} | {_fmt(v.get('sensibilite'))} | {_fmt(v.get('specificite'))} |"
                  for g, v in groups.items()]
        lines.append("")
    if "validation_externe" in m["evaluation"]:
        e = m["evaluation"]["validation_externe"]
        lines += [f"## Validation externe — site {e['site']} (n = {e['n']})", "",
                  f"ROC-AUC {_fmt(e['roc_auc'])} · PR-AUC {_fmt(e['pr_auc'])} · sensibilité (moyen+) "
                  f"{_fmt(e['orientation_moyen_ou_plus']['sensibilite'])}", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pathology", required=True, choices=["sein", "col", "ovaire", "endometre"])
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--data-source", default=None, help="Provenance des données (traçabilité)")
    parser.add_argument("--external-site", help="Valeur de `site` réservée à la validation externe")
    parser.add_argument("--target-sensitivity", type=float, default=0.95)
    parser.add_argument("--target-specificity", type=float, default=0.90)
    parser.add_argument("--n-iter", type=int, default=15, help="Itérations de la recherche d'hyperparamètres")
    parser.add_argument("--no-activate", action="store_true", help="Ne pas déployer cette version")
    parser.add_argument("--no-monotone", action="store_true",
                        help="Désactiver les contraintes de monotonie cliniques (déconseillé, pour comparaison uniquement)")
    parser.add_argument("--no-missing-indicators", action="store_true",
                        help="Ne pas créer d'indicatrices de manque (si le manque est un artefact du jeu source)")
    args = parser.parse_args()
    source = args.data_source or ("synthetique" if "synthetique" in args.data.name else args.data.name)
    meta = train(pd.read_csv(args.data), args.pathology, external_site=args.external_site,
                 target_sensitivity=args.target_sensitivity, target_specificity=args.target_specificity,
                 n_iter=args.n_iter, data_source=source, activate=not args.no_activate,
                 missing_indicators=not args.no_missing_indicators, monotone=not args.no_monotone)
    print(json.dumps(meta["evaluation"]["test"]["orientation_moyen_ou_plus"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
