"""Soumission d'un dépistage : vérification, appel au moteur IA, traçabilité et proposition d'orientation."""

import logging
from datetime import date

from sqlalchemy.orm import Session

from app.models import (
    ErrorEvent, Patient, Pathology, Referral, ReferralStatus, RiskAssessment, RiskLevel, Screening, ScreeningStatus, User, utcnow,
)
from app.services import engine_client, orientation
from app.services.audit import audit
from app.services.forms import check_form, ml_features

log = logging.getLogger(__name__)


def patient_age(patient: Patient, on: date) -> int | None:
    if patient.birth_date:
        b = patient.birth_date
        return on.year - b.year - ((on.month, on.day) < (b.month, b.day))
    if patient.birth_year_estimated:
        return on.year - patient.birth_year_estimated
    return None


def _upsert_referral(db: Session, screening: Screening, level: RiskLevel | None, text: str) -> None:
    referral = screening.referral
    if referral is None:
        referral = Referral(screening_id=screening.id, patient_id=screening.patient_id, status=ReferralStatus.PROPOSED)
        db.add(referral)
        screening.referral = referral
    # Une décision déjà prise par un professionnel n'est jamais écrasée par une nouvelle analyse.
    if referral.final_decision is None:
        referral.proposed_level = level
        referral.proposed_recommendation = text


def run_analysis(db: Session, screening: Screening, user: User) -> RiskAssessment | None:
    """Exécute le modèle IA. Si le moteur est indisponible, le dépistage reste « soumis » (analyse différée)."""
    check = check_form(screening.pathology, screening.data)
    screening.alerts = check.alerts
    age = patient_age(screening.patient, (screening.submitted_at or utcnow()).date())
    features = ml_features(screening.pathology, check.cleaned, age)

    try:
        result = engine_client.predict(screening.pathology, features)
    except engine_client.EngineUnavailable as exc:
        log.warning("Analyse différée pour %s : %s", screening.id, exc)
        if exc.server_error:
            # Même transaction que la requête (une session séparée verrouillerait SQLite et dupliquerait l'écriture)
            err = exc.server_error
            db.add(ErrorEvent(source="engine", message=err["message"], request_id=err["request_id"], path="/predict",
                              user_id=user.id, details={"body": err["body"]}))
        screening.status = ScreeningStatus.SUBMITTED
        level, text = orientation.propose(Pathology(screening.pathology), None, check.alerts)
        _upsert_referral(db, screening, level, text)
        audit(db, user, "ai_deferred", "screening", screening.id, {"reason": str(exc)})
        return None

    assessment = RiskAssessment(
        screening_id=screening.id,
        pathology=screening.pathology,
        model_id=result["model_id"],
        model_version=result["model_version"],
        model_validated=result.get("validated", False),
        score=result["score"],
        risk_level=RiskLevel(result["risk_level"]),
        explanations=result.get("explanations", []),
        features_sent=features,
    )
    db.add(assessment)
    screening.assessments.insert(0, assessment)
    screening.status = ScreeningStatus.ANALYSED
    level, text = orientation.propose(Pathology(screening.pathology), assessment.risk_level, check.alerts)
    _upsert_referral(db, screening, level, text)
    audit(db, user, "ai_run", "screening", screening.id, {
        "model_id": assessment.model_id, "model_version": assessment.model_version,
        "risk_level": assessment.risk_level.value, "score": round(assessment.score, 4),
    })
    return assessment
