"""Chargement des formulaires partagés, validation des saisies, signes d'alerte et extraction des variables IA."""

import json
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from typing import Any

from app.core.config import get_settings

UNKNOWN = "inconnu"


@lru_cache
def load_forms() -> dict[str, dict]:
    forms = {}
    for path in sorted(get_settings().forms_dir.glob("*.json")):
        form = json.loads(path.read_text(encoding="utf-8"))
        forms[form["pathology"]] = form
    return forms


def get_form(pathology: str) -> dict:
    try:
        return load_forms()[pathology]
    except KeyError:
        raise ValueError(f"Formulaire inconnu : {pathology}") from None


def iter_fields(form: dict):
    for section in form["sections"]:
        for f in section["fields"]:
            yield section, f


def is_missing(value: Any) -> bool:
    return value is None or value == "" or value == []


def is_visible(f: dict, data: dict) -> bool:
    cond = f.get("show_if")
    if not cond:
        return True
    other = data.get(cond["field"])
    if "equals" in cond:
        return other == cond["equals"]
    if "greater_than" in cond:
        return isinstance(other, (int, float)) and not isinstance(other, bool) and other > cond["greater_than"]
    return True


@dataclass
class FormCheck:
    errors: dict[str, str] = field(default_factory=dict)
    missing_required: list[str] = field(default_factory=list)
    alerts: list[dict] = field(default_factory=list)
    cleaned: dict[str, Any] = field(default_factory=dict)

    @property
    def is_complete(self) -> bool:
        return not self.errors and not self.missing_required


def _check_value(f: dict, value: Any) -> str | None:
    t = f["type"]
    options = {o["value"] for o in f.get("options", [])}
    if t == "boolean":
        if value not in (True, False, UNKNOWN):
            return "Valeur attendue : oui, non ou inconnu"
    elif t in ("integer", "number"):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return "Valeur numérique attendue"
        if t == "integer" and not float(value).is_integer():
            return "Nombre entier attendu"
        if "min" in f and value < f["min"]:
            return f"Valeur minimale : {f['min']}"
        if "max" in f and value > f["max"]:
            return f"Valeur maximale : {f['max']}"
    elif t == "choice":
        if value not in options:
            return "Option non reconnue"
    elif t == "multichoice":
        if not isinstance(value, list) or any(v not in options for v in value):
            return "Options non reconnues"
    elif t == "text":
        if not isinstance(value, str) or len(value) > 5000:
            return "Texte attendu (5000 caractères max.)"
    elif t == "date":
        try:
            date.fromisoformat(value)
        except (TypeError, ValueError):
            return "Date attendue (AAAA-MM-JJ)"
    return None


def _alert_for(f: dict, value: Any) -> dict | None:
    if "alert_when" in f and value == f["alert_when"]:
        return {"field": f["id"], "label": f["label"]}
    alert_opts = {o["value"]: o["label"] for o in f.get("options", []) if o.get("alert")}
    values = value if isinstance(value, list) else [value]
    hits = [alert_opts[v] for v in values if v in alert_opts]
    if hits:
        return {"field": f["id"], "label": f"{f['label']} : {', '.join(hits)}"}
    return None


def check_form(pathology: str, data: dict) -> FormCheck:
    """Valide les valeurs, ignore les champs masqués ou inconnus, relève les champs obligatoires manquants et les signes d'alerte."""
    form = get_form(pathology)
    result = FormCheck()
    for _, f in iter_fields(form):
        fid = f["id"]
        if not is_visible(f, data):
            continue
        value = data.get(fid)
        if is_missing(value):
            if f.get("required"):
                result.missing_required.append(fid)
            continue
        error = _check_value(f, value)
        if error:
            result.errors[fid] = error
            continue
        result.cleaned[fid] = value
        alert = _alert_for(f, value)
        if alert:
            result.alerts.append(alert)
    return result


def ml_features(pathology: str, cleaned: dict, age: int | None) -> dict[str, Any]:
    """Variables transmises au moteur IA : uniquement les champs `ml`, plus l'âge. Aucune donnée identifiante."""
    form = get_form(pathology)
    features: dict[str, Any] = {"age": age}
    for _, f in iter_fields(form):
        if f.get("ml"):
            features[f["id"]] = cleaned.get(f["id"])
    return features


def after_result_fields(pathology: str) -> dict[str, dict]:
    """Questions posées après le résultat de l'IA (« after_result ») : jamais exigées à la soumission."""
    return {f["id"]: f for _, f in iter_fields(get_form(pathology)) if f.get("after_result")}


def check_after_result(pathology: str, notes: dict) -> tuple[dict, dict[str, str]]:
    """Valide une appréciation post-résultat : seuls les champs « after_result » sont acceptés."""
    allowed = after_result_fields(pathology)
    cleaned, errors = {}, {}
    for key, value in notes.items():
        f = allowed.get(key)
        if f is None:
            errors[key] = "Champ non modifiable après l'analyse"
            continue
        if is_missing(value):
            cleaned[key] = None
            continue
        err = _check_value(f, value)
        if err:
            errors[key] = err
        else:
            cleaned[key] = value
    return cleaned, errors

