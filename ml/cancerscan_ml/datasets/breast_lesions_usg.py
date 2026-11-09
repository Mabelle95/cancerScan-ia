"""Import du jeu BrEaST-Lesions_USG vers le format d'entraînement du formulaire « sein ».

Source : Pawłowska A. et al., « Curated benchmark dataset for ultrasound based breast lesion analysis »,
Scientific Data 11, 148 (2024), doi:10.1038/s41597-024-02984-z — The Cancer Imaging Archive, collection
BrEaST-Lesions_USG. Licence CC BY 4.0 (usage commercial autorisé, citation obligatoire).

Limites à garder en tête :
- population : 256 femmes polonaises ayant TOUTES une lésion vue à l'échographie (pas une population de
  dépistage) ; prévalence ~38 % ;
- seules les variables observables par un agent de santé sont reprises (signes, antécédents, âge) ; les
  descripteurs échographiques et le BI-RADS ne le sont pas ;
- les champs du formulaire absents du jeu restent MANQUANTS (jamais « non ») ;
- les cas sans signes cliniques renseignés (« not available ») sont exclus par défaut : ces champs sont
  obligatoires dans CancerScan, et ces cas sont malins à 57 % dans BrEaST — le modèle apprendrait sinon que
  « donnée manquante = cancer », un artefact qui gonflerait les performances.

Usage :
    python -m cancerscan_ml.datasets.breast_lesions_usg --xlsx data/breast/BrEaST-clinical.xlsx \\
        --out data/breast/sein_breast_lesions_usg.csv
"""

import argparse
from pathlib import Path

import pandas as pd

NA = "not available"
SOURCE = "BrEaST-Lesions_USG (TCIA, CC BY 4.0)"


def _items(value) -> set[str] | None:
    """`a&b&c` → {a, b, c} ; « not available » → None (inconnu) ; « no » → ensemble vide."""
    if pd.isna(value) or str(value).strip() == NA:
        return None
    v = str(value).strip()
    return set() if v == "no" else {x.strip() for x in v.split("&")}


def _flag(items: set[str] | None, *keys: str):
    if items is None:
        return None
    return any(k in items for k in keys)


def convert(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in df.iterrows():
        signs, symptoms = _items(r["Signs"]), _items(r["Symptoms"])
        age = pd.to_numeric(r["Age"], errors="coerce")
        if symptoms is None:
            ecoulement = None
        else:
            ecoulement = "non_precise" if "nipple discharge" in symptoms else "aucun"
        rows.append({
            "patient_id": f"BREAST-{int(r['CaseID']):03d}",
            "site": "BrEaST-PL",
            "target": 1 if r["Classification"] == "malignant" else 0,
            "verification": r["Verification"],
            "age": None if pd.isna(age) else float(age),
            # Signes cliniques
            "masse_presente": _flag(signs, "palpable"),
            "modif_peau": _flag(signs, "skin retraction", "redness", "warmth", "peau d'orange", "peau d`orange"),
            "retraction_mamelon": _flag(signs, "nipple retraction"),
            # Antécédents et symptômes déclarés
            "atcd_familial_sein_ovaire": _flag(symptoms, "family history of breast/ovarian cancer"),
            "atcd_personnel_sein": _flag(symptoms, "personal history of breast cancer"),
            "traitement_hormonal": _flag(symptoms, "HRT/hormonal contraception"),
            "ecoulement": ecoulement,
        })
    out = pd.DataFrame(rows)
    # Booléens nullables : None reste une valeur manquante dans le CSV
    for col in ("masse_presente", "modif_peau", "retraction_mamelon", "atcd_familial_sein_ovaire",
                "atcd_personnel_sein", "traitement_hormonal"):
        out[col] = out[col].astype("boolean")
    return out


def unmapped_values(df: pd.DataFrame) -> dict[str, set[str]]:
    """Modalités rencontrées non reprises dans le formulaire (pour vérifier qu'aucune n'est oubliée)."""
    known_signs = {"palpable", "skin retraction", "redness", "warmth", "peau d'orange", "peau d`orange", "nipple retraction"}
    known_symptoms = {"family history of breast/ovarian cancer", "personal history of breast cancer",
                      "HRT/hormonal contraception", "nipple discharge"}
    seen = {"Signs": set(), "Symptoms": set()}
    for col in seen:
        for v in df[col]:
            seen[col] |= _items(v) or set()
    return {"Signs": seen["Signs"] - known_signs, "Symptoms": seen["Symptoms"] - known_symptoms}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--xlsx", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--keep-missing-signs", action="store_true", help="Conserver les cas sans signes renseignés")
    args = parser.parse_args()
    raw = pd.read_excel(args.xlsx, sheet_name=0)
    out = convert(raw)
    if not args.keep_missing_signs:
        excluded = out["masse_presente"].isna()
        print(f"{int(excluded.sum())} cas exclus (signes cliniques non renseignés)")
        out = out[~excluded]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    print(f"{len(out)} cas, {int(out['target'].sum())} malins ({out['target'].mean():.0%}) → {args.out}")
    print("Taux de manquant :", out.drop(columns=["patient_id", "site", "target", "verification"]).isna().mean().round(2).to_dict())
    print("Modalités non reprises :", unmapped_values(raw))


if __name__ == "__main__":
    main()
