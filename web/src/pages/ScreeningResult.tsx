import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Facility, type Referral, type ReferralStatus, type Screening } from "../api";
import { useAuth } from "../auth";
import {
  Card, ErrorNotice, Explanations, Loading, PATHOLOGY_LABELS, REFERRAL_LABELS, RiskBadge, StatusBadge, formatDate, useAsync,
} from "../components/ui";
import { useForms } from "../components/useForms";
import { displayValue, isAlert, isMissing } from "../formLogic";

export function ScreeningResult() {
  const { sid = "" } = useParams();
  const { can } = useAuth();
  const screening = useAsync(() => api.screening(sid), [sid]);
  const patient = useAsync(() => (screening.data ? api.patient(screening.data.patient_id) : Promise.resolve(null)), [screening.data?.patient_id]);
  const facilities = useAsync(() => api.facilities(), []);
  const { byPathology } = useForms();
  const [retrying, setRetrying] = useState(false);

  if (screening.loading) return <Loading />;
  if (screening.error || !screening.data) return <ErrorNotice message={screening.error ?? "Dépistage introuvable"} />;
  const s = screening.data;
  const a = s.assessments[0];
  const ref = s.referral;
  const form = byPathology(s.pathology);
  const facilityName = (id: number | null) => facilities.data?.find((f) => f.id === id)?.name ?? "—";

  const retry = async () => {
    setRetrying(true);
    try { await api.processPending(); screening.reload(); } finally { setRetrying(false); }
  };

  return (
    <>
      <div className="page-head">
        <div>
          <p className="muted small" style={{ margin: 0 }}>
            <Link to="/patients">Patientes</Link> / {patient.data && <Link to={`/patients/${s.patient_id}`}>{patient.data.full_name ?? patient.data.code}</Link>} /
          </p>
          <h1>Dépistage — {PATHOLOGY_LABELS[s.pathology]}</h1>
          <div className="row"><StatusBadge status={s.status} /><span className="muted small">{formatDate(s.submitted_at ?? s.created_at, true)} · formulaire v{s.form_version}</span></div>
        </div>
        {can("screenings:write") && s.status !== "valide" && (
          <Link className="btn" to={`/depistages/${s.id}/modifier`}>{s.status === "brouillon" ? "Reprendre la saisie" : "Corriger les données"}</Link>
        )}
      </div>

      {s.alerts.length > 0 && (
        <div className="notice notice-danger"><strong>Signe(s) d'alerte</strong>{s.alerts.map((x) => x.label).join(" · ")}. Une évaluation médicale est nécessaire même si le risque estimé est faible.</div>
      )}

      <div className="grid grid-2">
        <Card title="Estimation du risque">
          {s.status === "brouillon" && <p className="muted">Dépistage non soumis : complétez le formulaire pour obtenir une analyse.</p>}
          {s.status === "soumis" && (
            <div className="notice notice-warn">
              <strong>Analyse IA pas encore calculée</strong>
              Le moteur IA n'était pas disponible ou aucun modèle validé n'est déployé. L'orientation peut être décidée par le professionnel sans attendre.
              <div style={{ marginTop: 8 }}><button className="btn btn-sm" onClick={retry} disabled={retrying}>{retrying ? "Nouvel essai…" : "Relancer l'analyse"}</button></div>
            </div>
          )}
          {a && (
            <>
              <div className="row" style={{ marginBottom: 12 }}>
                <RiskBadge level={a.risk_level} large />
                <span className="muted">Score estimé : {(a.score * 100).toFixed(0)} %</span>
              </div>
              {!a.model_validated && (
                <div className="notice notice-warn"><strong>Modèle non validé cliniquement</strong>Résultat à usage de démonstration et de développement : il ne doit pas guider une décision médicale.</div>
              )}
              <h3>Facteurs ayant le plus pesé</h3>
              <Explanations items={a.explanations} format={(feature, value) => {
                if (value === null || value === undefined || value === "inconnu") return "non renseigné";
                if (feature === "age") return `${value} ans`;
                const field = form?.sections.flatMap((x) => x.fields).find((f) => f.id === feature);
                return field ? displayValue(field, value) : String(value);
              }} />
              <p className="field-help">Modèle {a.model_id} v{a.model_version} · calculé le {formatDate(a.created_at, true)}</p>
            </>
          )}
          <p className="field-help" style={{ marginTop: 8 }}>
            Un risque faible ne signifie jamais qu'un cancer est absent. Le diagnostic relève des professionnels de santé.
          </p>
        </Card>

        <Card title="Orientation">
          {ref ? (
            <>
              <div className="row" style={{ marginBottom: 8 }}>
                <span className="muted">Proposée :</span><RiskBadge level={ref.proposed_level} />
                <span className="badge">{REFERRAL_LABELS[ref.status]}</span>
              </div>
              <p>{ref.proposed_recommendation}</p>
              {ref.final_decision ? (
                <div className="notice notice-ok" style={{ marginTop: 12 }}>
                  <strong>Décision du professionnel ({formatDate(ref.decided_at)})</strong>
                  {ref.final_decision}
                  <dl className="dl" style={{ marginTop: 8 }}>
                    <dt>Structure de référence</dt><dd>{facilityName(ref.to_facility_id)}</dd>
                    <dt>Rendez-vous</dt><dd>{formatDate(ref.appointment_date)}</dd>
                    {ref.reason && <><dt>Motif</dt><dd>{ref.reason}</dd></>}
                  </dl>
                </div>
              ) : can("referrals:decide") ? (
                <DecisionForm referral={ref} facilities={facilities.data ?? []} onDone={screening.reload} />
              ) : (
                <div className="notice notice-info">En attente de validation par un médecin ou un spécialiste.</div>
              )}
              {ref.final_decision && <StatusActions referral={ref} onDone={screening.reload} />}
            </>
          ) : <p className="muted">L'orientation sera proposée après la soumission.</p>}
        </Card>
      </div>

      {form && <DataRecap screening={s} form={form} />}
    </>
  );
}

function DecisionForm({ referral, facilities, onDone }: { referral: Referral; facilities: Facility[]; onDone: () => void }) {
  const [decision, setDecision] = useState(referral.proposed_recommendation);
  const [facility, setFacility] = useState("");
  const [date, setDate] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.decideReferral(referral.id, {
        final_decision: decision, to_facility_id: facility ? Number(facility) : null, appointment_date: date || null, reason: reason || undefined,
      });
      onDone();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} style={{ marginTop: 12, borderTop: "1px solid var(--border)", paddingTop: 12 }}>
      <h3>Valider la conduite à tenir</h3>
      <ErrorNotice message={error} />
      <label className="field"><span className="field-label">Décision<span className="req">*</span></span>
        <textarea required minLength={3} value={decision} onChange={(e) => setDecision(e.target.value)} />
        <span className="field-help">Confirmez ou adaptez la proposition selon votre évaluation clinique.</span></label>
      <label className="field"><span className="field-label">Structure de référence</span>
        <select value={facility} onChange={(e) => setFacility(e.target.value)}>
          <option value="">— Pas de référence —</option>
          {facilities.map((f) => <option key={f.id} value={f.id}>{f.name} ({f.region})</option>)}
        </select></label>
      <div className="grid grid-2">
        <label className="field"><span className="field-label">Date de rendez-vous</span>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
        <label className="field"><span className="field-label">Motif</span>
          <input type="text" value={reason} onChange={(e) => setReason(e.target.value)} /></label>
      </div>
      <button className="btn btn-primary" disabled={busy}>Valider l'orientation</button>
    </form>
  );
}

const NEXT_STATUS: Partial<Record<ReferralStatus, ReferralStatus[]>> = {
  proposee: ["annulee"],
  programmee: ["realisee", "perdue_de_vue", "annulee"],
  perdue_de_vue: ["programmee", "realisee"],
};

function StatusActions({ referral, onDone }: { referral: Referral; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const options = NEXT_STATUS[referral.status] ?? [];
  if (!options.length) return null;
  const change = async (status: ReferralStatus) => {
    setBusy(true);
    try { await api.referralStatus(referral.id, status); onDone(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <div style={{ marginTop: 12 }}>
      <ErrorNotice message={error} />
      <span className="muted small">Mettre à jour le suivi : </span>
      <div className="row" style={{ marginTop: 6 }}>
        {options.map((st) => <button key={st} className="btn btn-sm" disabled={busy} onClick={() => change(st)}>{REFERRAL_LABELS[st]}</button>)}
      </div>
    </div>
  );
}

function DataRecap({ screening, form }: { screening: Screening; form: NonNullable<ReturnType<ReturnType<typeof useForms>["byPathology"]>> }) {
  return (
    <Card title="Données saisies">
      <div className="grid grid-2">
        {form.sections.map((section) => {
          const fields = section.fields.filter((f) => !isMissing(screening.data[f.id]));
          if (!fields.length) return null;
          return (
            <div key={section.id}>
              <h3>{section.title}</h3>
              <dl className="dl">
                {fields.map((f) => (
                  <div key={f.id} style={{ display: "contents" }}>
                    <dt>{f.label}</dt>
                    <dd className={isAlert(f, screening.data[f.id]) ? "alert-value" : undefined}>{displayValue(f, screening.data[f.id])}</dd>
                  </div>
                ))}
              </dl>
            </div>
          );
        })}
      </div>
      {screening.form_version !== form.version && (
        <p className="field-help">Saisi avec la version {screening.form_version} du formulaire (version actuelle : {form.version}).</p>
      )}
    </Card>
  );
}
