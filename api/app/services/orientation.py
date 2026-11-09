"""Recommandations d'orientation proposées selon le niveau de risque.

⚠️ Textes provisoires : à valider par les professionnels de santé avant tout usage clinique.
"""

from app.models import Pathology, RiskLevel

_ORDER = [RiskLevel.FAIBLE, RiskLevel.MOYEN, RiskLevel.ELEVE]

RECOMMENDATIONS: dict[RiskLevel, str] = {
    RiskLevel.FAIBLE: "Conseils de prévention et suivi selon les recommandations médicales en vigueur.",
    RiskLevel.MOYEN: "Consultation et évaluation spécialisée dans un délai adapté.",
    RiskLevel.ELEVE: "Référence prioritaire vers une structure spécialisée pour évaluation rapide.",
}

PATHOLOGY_HINTS: dict[Pathology, dict[RiskLevel, str]] = {
    Pathology.SEIN: {
        RiskLevel.MOYEN: "Évaluation clinique et imagerie mammaire (échographie / mammographie) selon disponibilité.",
        RiskLevel.ELEVE: "Imagerie mammaire et avis spécialisé en priorité ; biopsie si indiquée par le spécialiste.",
    },
    Pathology.COL: {
        RiskLevel.MOYEN: "Dépistage du col (IVA/IVL, test HPV ou cytologie) et suivi selon le résultat.",
        RiskLevel.ELEVE: "Colposcopie et avis gynécologique en priorité.",
    },
    Pathology.OVAIRE: {
        RiskLevel.MOYEN: "Examen gynécologique et échographie pelvienne.",
        RiskLevel.ELEVE: "Échographie pelvienne et avis gynécologique en priorité.",
    },
    Pathology.ENDOMETRE: {
        RiskLevel.MOYEN: "Examen gynécologique et échographie pelvienne endovaginale.",
        RiskLevel.ELEVE: "Avis gynécologique en priorité pour exploration de l'endomètre.",
    },
}

ALERT_NOTE = (
    "Signe(s) d'alerte relevé(s) à la saisie : une évaluation médicale est nécessaire "
    "quel que soit le score estimé par le modèle."
)


def max_level(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    return a if _ORDER.index(a) >= _ORDER.index(b) else b


def propose(pathology: Pathology, model_level: RiskLevel | None, alerts: list) -> tuple[RiskLevel | None, str]:
    """Niveau d'orientation proposé et texte associé.

    Un signe d'alerte impose au minimum une évaluation (niveau « moyen ») même si le modèle estime
    un risque faible ou si l'analyse IA n'a pas encore été calculée.
    """
    level = model_level
    if alerts:
        level = max_level(level or RiskLevel.MOYEN, RiskLevel.MOYEN)
    if level is None:
        return None, "Analyse IA en attente : orientation à définir par le professionnel de santé."
    parts = [RECOMMENDATIONS[level]]
    hint = PATHOLOGY_HINTS.get(pathology, {}).get(level)
    if hint:
        parts.append(hint)
    if alerts:
        parts.append(ALERT_NOTE)
    return level, " ".join(parts)
