"""Statistiques agrégées pour les responsables sanitaires (aucune donnée identifiante).

Les effectifs non nuls inférieurs à `stats_min_cell_size` sont masqués (`null`) pour limiter le risque de
ré-identification. Les médecins ne voient que les statistiques de leur établissement.
"""

from collections import Counter, defaultdict
from datetime import date
from statistics import median

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.core.config import get_settings
from app.core.permissions import Perm, Role
from app.deps import DbSession, require
from app.models import ExamResult, Patient, Pathology, Referral, ReferralStatus, Screening, ScreeningStatus
from app.services.analysis import patient_age
from app.services.audit import audit

router = APIRouter(prefix="/stats", tags=["Statistiques"])

AGE_BRACKETS = [(0, 29), (30, 39), (40, 49), (50, 59), (60, 69), (70, 200)]


def _bracket(age: int | None) -> str:
    if age is None:
        return "inconnu"
    for lo, hi in AGE_BRACKETS:
        if lo <= age <= hi:
            return f"{lo}-{hi}" if hi < 200 else f"{lo}+"
    return "inconnu"


def _mask(counter: dict, k: int) -> dict:
    return {key: (n if n == 0 or n >= k else None) for key, n in counter.items()}


@router.get("/overview")
def overview(
    db: DbSession,
    request: Request,
    user=require(Perm.STATS_READ),
    date_from: date | None = None,
    date_to: date | None = None,
    region: str | None = None,
    pathology: Pathology | None = None,
):
    k = get_settings().stats_min_cell_size
    q = (
        select(Screening, Patient)
        .join(Patient, Patient.id == Screening.patient_id)
        .where(Screening.status != ScreeningStatus.DRAFT)
    )
    if user.role == Role.MEDECIN:
        q = q.where(Screening.facility_id == user.facility_id)
    if region:
        q = q.where(Patient.region == region)
    if pathology:
        q = q.where(Screening.pathology == pathology)
    if date_from:
        q = q.where(Screening.submitted_at >= date_from)
    if date_to:
        q = q.where(Screening.submitted_at < date.fromordinal(date_to.toordinal() + 1))

    rows = db.execute(q).all()
    patients: set = set()
    by_pathology, by_region, by_age, by_risk, by_month = Counter(), Counter(), Counter(), Counter(), Counter()
    referral_status, alerts = Counter(), 0
    delays_days: list[int] = []
    region_risk: dict[str, Counter] = defaultdict(Counter)

    for s, p in rows:
        patients.add(p.id)
        when = s.submitted_at or s.created_at
        by_pathology[s.pathology] += 1
        by_region[p.region] += 1
        by_age[_bracket(patient_age(p, when.date()))] += 1
        by_month[when.strftime("%Y-%m")] += 1
        alerts += bool(s.alerts)
        level = s.assessments[0].risk_level.value if s.assessments else "en_attente"
        by_risk[level] += 1
        region_risk[p.region][level] += 1
        r = s.referral
        if r and r.final_decision:
            referral_status[r.status.value] += 1
            if r.status == ReferralStatus.COMPLETED and r.completed_at:
                delays_days.append((r.completed_at.date() - when.date()).days)

    referred = sum(referral_status[st] for st in ("programmee", "realisee", "perdue_de_vue"))
    completed = referral_status["realisee"]

    exam_q = select(ExamResult.conclusion).join(Patient, Patient.id == ExamResult.patient_id)
    if user.role == Role.MEDECIN:
        exam_q = exam_q.where(Patient.facility_id == user.facility_id)
    if region:
        exam_q = exam_q.where(Patient.region == region)
    confirmed = Counter(c for c in db.scalars(exam_q) if c in ("malin", "precancereux"))

    audit(db, user, "read", "stats", details={"region": region, "pathology": pathology})
    db.commit()
    return {
        "scope": "etablissement" if user.role == Role.MEDECIN else "national",
        "min_cell_size": k,
        "totals": {
            "patientes": len(patients),
            "depistages": len(rows),
            "avec_signes_alerte": alerts,
            "references": referred,
            "references_realisees": completed,
            "taux_realisation": round(completed / referred, 3) if referred >= k else None,
            "delai_median_jours": median(delays_days) if len(delays_days) >= k else None,
            "cas_confirmes": _mask(confirmed, k),
        },
        "par_pathologie": _mask(by_pathology, k),
        "par_region": _mask(by_region, k),
        "par_tranche_age": _mask(by_age, k),
        "par_niveau_risque": _mask(by_risk, k),
        "risque_par_region": {reg: _mask(c, k) for reg, c in region_risk.items()},
        "statut_references": _mask(referral_status, k),
        "evolution_mensuelle": dict(sorted(_mask(by_month, k).items())),
    }
