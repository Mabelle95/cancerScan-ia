"""Génération de données SYNTHÉTIQUES pour tester le pipeline de bout en bout.

⚠️ Ces données sont fictives : elles ne reflètent aucune réalité épidémiologique. Un modèle entraîné dessus
est marqué `data_source = "synthetique"` et ne peut pas être promu en modèle validé.

Usage : python -m cancerscan_ml.synthetic --pathology sein --n 3000 --out data/sein_synthetique.csv
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from cancerscan_ml.features import load_form

SITES = ["Maritime", "Plateaux", "Centrale", "Kara", "Savanes"]


def generate(pathology: str, n: int, seed: int = 42, prevalence_shift: float = -5.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    form = load_form(pathology)
    n_patients = int(n * 0.8)
    patient_ids = rng.integers(0, n_patients, size=n)  # ~20 % de patientes revues plusieurs fois
    age_by_patient = rng.normal(45, 12, size=n_patients).clip(18, 90).round()

    data = {"patient_id": [f"P{p:06d}" for p in patient_ids], "site": rng.choice(SITES, size=n),
            "age": age_by_patient[patient_ids]}
    logit = prevalence_shift + 0.04 * (data["age"] - 45)

    for section in form["sections"]:
        for f in section["fields"]:
            if not f.get("ml"):
                continue
            missing = rng.random(n) < 0.08
            if f["type"] == "boolean":
                p = 0.10 if f.get("alert_when") is True else 0.25
                values = rng.random(n) < p
                weight = 1.6 if f.get("alert_when") is True else (0.6 if f.get("required") else 0.25)
                logit = logit + weight * values
                col = np.where(missing, None, values).astype(object)
            elif f["type"] in ("integer", "number"):
                lo, hi = f.get("min", 0), f.get("max", 100)
                values = rng.gamma(2.0, (hi - lo) / 12, size=n).clip(lo, hi)
                values = values.round() if f["type"] == "integer" else values.round(1)
                col = np.where(missing, np.nan, values)
            else:
                opts = [o for o in f["options"]]
                weights = np.array([0.08 if o.get("alert") else 1.0 for o in opts])
                idx = rng.choice(len(opts), size=n, p=weights / weights.sum())
                logit = logit + np.array([1.8 if opts[i].get("alert") else 0.0 for i in idx])
                col = np.where(missing, None, np.array([opts[i]["value"] for i in idx], dtype=object))
            data[f["id"]] = col

    prob = 1 / (1 + np.exp(-logit))
    data["target"] = (rng.random(n) < prob).astype(int)
    df = pd.DataFrame(data)
    # Cohérence par patiente : une patiente confirmée positive l'est pour toutes ses observations
    df["target"] = df.groupby("patient_id")["target"].transform("max")
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pathology", required=True, choices=["sein", "col", "ovaire", "endometre"])
    parser.add_argument("--n", type=int, default=3000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    df = generate(args.pathology, args.n, args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"{len(df)} lignes synthétiques écrites dans {args.out} (prévalence {df['target'].mean():.1%})")


if __name__ == "__main__":
    main()
