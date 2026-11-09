"""Encodage des variables à partir des formulaires partagés (`shared/forms`).

Le même code est utilisé à l'entraînement et par le moteur d'inférence, ce qui garantit que les
variables sont préparées de façon identique dans les deux cas.

Règles :
- booléen : oui → 1, non → 0, « inconnu » ou absent → valeur manquante (NaN) ;
- numérique : valeur ou NaN ;
- choix : modalité textuelle ; absent → « manquant » (distinct d'une réponse négative).
Les valeurs manquantes sont imputées dans le pipeline, avec une variable indicatrice de manque.
"""

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parents[2]
FORMS_DIR = Path(os.environ.get("FORMS_DIR", ROOT / "shared" / "forms"))
MISSING_CATEGORY = "manquant"


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    kind: str  # numeric | boolean | categorical
    label: str
    categories: tuple[str, ...] = ()
    # +1 : ne peut qu'augmenter le risque (déclaré « "monotone": "increasing" » dans le formulaire) ; 0 : libre
    monotone: int = 0


_MONOTONE = {"increasing": 1, "decreasing": -1}


@lru_cache
def load_form(pathology: str) -> dict:
    path = FORMS_DIR / f"{pathology}.json"
    if not path.exists():
        raise ValueError(f"Formulaire introuvable pour la pathologie « {pathology} »")
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache
def feature_specs(pathology: str) -> tuple[FeatureSpec, ...]:
    form = load_form(pathology)
    # Le risque de ces cancers augmente avec l'âge : contrainte croissante sauf indication contraire du formulaire
    specs = [FeatureSpec("age", "numeric", "Âge", monotone=_MONOTONE.get(form.get("age_monotone", "increasing"), 0))]
    for section in form["sections"]:
        for f in section["fields"]:
            if not f.get("ml"):
                continue
            mono = _MONOTONE.get(f.get("monotone", ""), 0)
            if f["type"] == "boolean":
                specs.append(FeatureSpec(f["id"], "boolean", f["label"], monotone=mono))
            elif f["type"] in ("integer", "number"):
                specs.append(FeatureSpec(f["id"], "numeric", f["label"], monotone=mono))
            elif f["type"] == "choice":
                specs.append(FeatureSpec(f["id"], "categorical", f["label"], tuple(o["value"] for o in f["options"])))
            else:
                raise ValueError(f"Type non pris en charge pour une variable ML : {f['id']} ({f['type']})")
    return tuple(specs)


def leading_constraints(pathology: str) -> tuple[int, ...]:
    """Contraintes des colonnes numériques/booléennes, dans l'ordre où `preprocessor` les place (en premier)."""
    return tuple(s.monotone for s in feature_specs(pathology) if s.kind in ("numeric", "boolean"))


def monotone_features(pathology: str) -> dict[str, str]:
    return {s.name: ("croissant" if s.monotone > 0 else "décroissant") for s in feature_specs(pathology) if s.monotone}


def form_version(pathology: str) -> str:
    return load_form(pathology)["version"]


def _encode_value(spec: FeatureSpec, value):
    if spec.kind == "boolean":
        # True/False ou 1/0 (fichiers CSV) ; « inconnu », None, NaN → manquant
        return {True: 1.0, False: 0.0}.get(value, np.nan)
    if spec.kind == "numeric":
        if value is None or value == "" or isinstance(value, bool):
            return np.nan
        try:
            return float(value)
        except (TypeError, ValueError):
            return np.nan
    if value is None or value == "":
        return MISSING_CATEGORY
    return str(value)


def to_frame(pathology: str, records: list[dict]) -> pd.DataFrame:
    """Transforme une liste de saisies (dict champ → valeur) en tableau prêt pour le pipeline."""
    specs = feature_specs(pathology)
    rows = [{s.name: _encode_value(s, r.get(s.name)) for s in specs} for r in records]
    df = pd.DataFrame(rows, columns=[s.name for s in specs])
    for s in specs:
        df[s.name] = df[s.name].astype(object if s.kind == "categorical" else float)
    return df


def preprocessor(pathology: str, scale: bool, missing_indicators: bool = True) -> ColumnTransformer:
    """Imputation (+ indicatrices de manque), standardisation optionnelle et one-hot encoding.

    Désactiver `missing_indicators` quand le manque est un artefact du jeu source (le modèle apprendrait
    sinon qu'une saisie incomplète modifie le risque).
    """
    specs = feature_specs(pathology)
    numeric = [s.name for s in specs if s.kind in ("numeric", "boolean")]
    categorical = [s for s in specs if s.kind == "categorical"]
    num_steps = [("impute", SimpleImputer(strategy="median", add_indicator=missing_indicators, keep_empty_features=True))]
    if scale:
        num_steps.append(("scale", StandardScaler()))
    if missing_indicators:
        # « manquant » est une modalité à part entière
        cat = OneHotEncoder(categories=[list(s.categories) + [MISSING_CATEGORY] for s in categorical],
                            handle_unknown="ignore", sparse_output=False)
    else:
        # « manquant » est remplacé par la modalité la plus fréquente : le manque ne porte aucune information
        cat = Pipeline([
            ("impute", SimpleImputer(missing_values=MISSING_CATEGORY, strategy="most_frequent", keep_empty_features=True)),
            ("onehot", OneHotEncoder(categories=[list(s.categories) for s in categorical],
                                     handle_unknown="ignore", sparse_output=False)),
        ])
    return ColumnTransformer(
        [
            ("num", Pipeline(num_steps), numeric),
            ("cat", cat, [s.name for s in categorical]),
        ],
        verbose_feature_names_out=False,
    )


def source_feature(transformed_name: str, pathology: str) -> str:
    """Retrouve la variable d'origine d'une colonne transformée (one-hot, indicatrice de manque)."""
    names = sorted((s.name for s in feature_specs(pathology)), key=len, reverse=True)
    if transformed_name.startswith("missingindicator_"):
        transformed_name = transformed_name[len("missingindicator_"):]
    for n in names:
        if transformed_name == n or transformed_name.startswith(n + "_"):
            return n
    return transformed_name
