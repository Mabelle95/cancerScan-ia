"""Métriques statistiques et cliniques (cahier des charges §6.7)."""

import numpy as np
from sklearn.calibration import calibration_curve
from sklearn.metrics import average_precision_score, brier_score_loss, confusion_matrix, roc_auc_score


def _safe(fn, *args):
    try:
        return round(float(fn(*args)), 4)
    except ValueError:  # une seule classe présente
        return None


def at_threshold(y, p, t) -> dict:
    pred = (p >= t).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    div = lambda a, b: round(a / b, 4) if b else None  # noqa: E731
    return {
        "seuil": round(float(t), 4),
        "sensibilite": div(tp, tp + fn), "specificite": div(tn, tn + fp),
        "vpp": div(tp, tp + fp), "vpn": div(tn, tn + fn),
        "exactitude": div(tp + tn, len(y)),
        "f1": div(2 * tp, 2 * tp + fp + fn),
        "vp": int(tp), "fp": int(fp), "fn": int(fn), "vn": int(tn),
    }


def choose_thresholds(y, p, target_sensitivity: float, target_specificity: float) -> dict:
    """Seuils proposés (à arrêter avec les professionnels de santé) :

    - « moyen » : seuil le plus haut garantissant la sensibilité cible → limite les faux négatifs ;
    - « élevé » : seuil le plus bas atteignant la spécificité cible, et toujours au-dessus du seuil « moyen ».
    """
    candidates = np.unique(np.round(p, 4))
    moyen = min(candidates)
    for t in candidates:
        if at_threshold(y, p, t)["sensibilite"] >= target_sensitivity:
            moyen = t
    eleve = max(candidates)
    for t in sorted(candidates, reverse=True):
        spec = at_threshold(y, p, t)["specificite"]
        if spec is not None and spec >= target_specificity:
            eleve = t
        else:
            break
    eleve = max(eleve, moyen + 1e-4)
    return {"moyen": round(float(moyen), 4), "eleve": round(float(eleve), 4)}


def evaluate(y, p, thresholds: dict) -> dict:
    y, p = np.asarray(y), np.asarray(p)
    levels = np.where(p >= thresholds["eleve"], "eleve", np.where(p >= thresholds["moyen"], "moyen", "faible"))
    try:
        frac_pos, mean_pred = calibration_curve(y, p, n_bins=10, strategy="quantile")
        calib = [{"prob_moyenne": round(float(m), 4), "frequence_observee": round(float(f), 4)} for m, f in zip(mean_pred, frac_pos)]
    except ValueError:
        calib = []
    return {
        "n": int(len(y)), "positifs": int(y.sum()), "prevalence": round(float(y.mean()), 4) if len(y) else None,
        "roc_auc": _safe(roc_auc_score, y, p),
        "pr_auc": _safe(average_precision_score, y, p),
        "brier": _safe(brier_score_loss, y, p),
        "orientation_moyen_ou_plus": at_threshold(y, p, thresholds["moyen"]),
        "orientation_eleve": at_threshold(y, p, thresholds["eleve"]),
        "repartition_niveaux": {
            lvl: {"n": int((levels == lvl).sum()), "positifs": int(y[levels == lvl].sum())} for lvl in ("faible", "moyen", "eleve")
        },
        "calibration": calib,
    }


def subgroups(y, p, groups, thresholds: dict, min_positives: int = 5) -> dict:
    """Performance par sous-groupe (tranche d'âge, région…) pour détecter des inégalités (§12.5)."""
    y, p, groups = np.asarray(y), np.asarray(p), np.asarray(groups)
    out = {}
    for g in sorted(set(groups.tolist()), key=str):
        mask = groups == g
        if y[mask].sum() < min_positives:
            out[str(g)] = {"n": int(mask.sum()), "positifs": int(y[mask].sum()), "note": "effectif insuffisant"}
            continue
        m = at_threshold(y[mask], p[mask], thresholds["moyen"])
        out[str(g)] = {"n": int(mask.sum()), "positifs": int(y[mask].sum()), "roc_auc": _safe(roc_auc_score, y[mask], p[mask]),
                       "sensibilite": m["sensibilite"], "specificite": m["specificite"]}
    return out
