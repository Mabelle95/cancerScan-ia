import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { Icon } from "../components/Icon";
import {
  Card, ErrorNotice, Loading, PATHOLOGY_LABELS, REFERRAL_LABELS, RiskBadge, StatusBadge, formatDate, patientAge, useAsync,
} from "../components/ui";

const EXAM_TYPES: Record<string, string> = {
  mammographie: "Mammographie", echographie_mammaire: "Échographie mammaire", echographie_pelvienne: "Échographie pelvienne",
  cytologie: "Cytologie", test_hpv: "Test HPV", biopsie: "Biopsie / anatomopathologie", autre: "Autre",
};
const CONCLUSIONS: Record<string, string> = {
  normal: "Normal", benin: "Bénin", suspect: "Suspect", precancereux: "Précancéreux", malin: "Malin", indetermine: "Indéterminé",
};

export function PatientDetail() {
  const { id = "" } = useParams();
  const { can } = useAuth();
  const navigate = useNavigate();
  const patient = useAsync(() => api.patient(id), [id]);
  const screenings = useAsync(() => api.patientScreenings(id), [id]);
  const exams = useAsync(() => api.patientExams(id), [id]);
  const [showExam, setShowExam] = useState(false);

  if (patient.loading) return <Loading />;
  if (patient.error || !patient.data) return <ErrorNotice message={patient.error ?? "Dossier introuvable"} />;
  const p = patient.data;

  return (
    <>
      <div className="page-head">
        <div>
          <p className="muted small" style={{ margin: 0 }}><Link to="/patients">Patientes</Link> /</p>
          <h1>{p.full_name ?? p.code}</h1>
          <div className="row muted">
            <span>{p.code}</span>·<span>{patientAge(p)}</span>·<span>{[p.locality, p.region].filter(Boolean).join(", ")}</span>
          </div>
        </div>
        {can("screenings:write") && <Link className="btn btn-hero" to={`/patients/${id}/depistage`}><Icon name="plus" />Nouveau dépistage</Link>}
      </div>

      <div className="grid grid-2">
        <Card title="Informations" icon="person">
          <dl className="dl">
            <dt>Téléphone</dt><dd>{p.phone ?? "—"}</dd>
            <dt>Niveau d'éducation</dt><dd>{p.education_level ?? "—"}</dd>
            <dt>Consentement</dt><dd>{p.consent_given ? `Oui, le ${formatDate(p.consent_date)}` : "Non"}</dd>
            <dt>Recherche</dt><dd>{p.consent_research ? "Accepte" : "Refuse / non demandé"}</dd>
            <dt>Dossier créé le</dt><dd>{formatDate(p.created_at)}</dd>
          </dl>
        </Card>

        <Card title="Examens complémentaires" icon="note" actions={can("exams:write") && (
          <button className="btn btn-sm" onClick={() => setShowExam(!showExam)}>{showExam ? "Fermer" : "Ajouter un résultat"}</button>
        )}>
          {showExam && <ExamForm patientId={id} screenings={screenings.data ?? []} onDone={() => { setShowExam(false); exams.reload(); }} />}
          <ErrorNotice message={exams.error} />
          {exams.data?.length ? (
            <ul style={{ paddingLeft: 18, margin: 0 }}>
              {exams.data.map((e) => (
                <li key={e.id} style={{ marginBottom: 6 }}>
                  <strong>{EXAM_TYPES[e.exam_type] ?? e.exam_type}</strong> — {formatDate(e.exam_date ?? e.created_at)}
                  {e.conclusion && <> · <span className={e.conclusion === "malin" ? "badge badge-alert" : "badge"}>{CONCLUSIONS[e.conclusion] ?? e.conclusion}</span></>}
                  <div className="small muted">{e.result}{e.source ? ` (${e.source})` : ""}</div>
                </li>
              ))}
            </ul>
          ) : !showExam && <p className="muted">Aucun examen enregistré.</p>}
        </Card>
      </div>

      <Card title="Historique des dépistages" icon="list">
        <ErrorNotice message={screenings.error} />
        {screenings.loading ? <Loading /> : screenings.data?.length ? (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Date</th><th>Pathologie</th><th>Statut</th><th>Risque estimé</th><th>Orientation</th></tr></thead>
              <tbody>
                {screenings.data.map((s) => (
                  <tr key={s.id} className="clickable" onClick={() => navigate(`/depistages/${s.id}`)}>
                    <td>{formatDate(s.submitted_at ?? s.created_at)}</td>
                    <td>{PATHOLOGY_LABELS[s.pathology]}{s.alerts.length > 0 && <span className="badge badge-alert" style={{ marginLeft: 6 }}>{s.alerts.length} alerte{s.alerts.length > 1 ? "s" : ""}</span>}</td>
                    <td><StatusBadge status={s.status} /></td>
                    <td>{s.assessments[0] ? <RiskBadge level={s.assessments[0].risk_level} compact /> : <RiskBadge level={null} compact />}</td>
                    <td>{s.referral ? REFERRAL_LABELS[s.referral.status] : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p className="muted">Aucun dépistage pour le moment.</p>}
      </Card>
    </>
  );
}

function ExamForm({ patientId, screenings, onDone }: { patientId: string; screenings: { id: string; pathology: string; created_at: string }[]; onDone: () => void }) {
  const [f, setF] = useState({ exam_type: "echographie_mammaire", result: "", conclusion: "", exam_date: "", source: "", screening_id: screenings[0]?.id ?? "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f, v: string) => setF({ ...f, [k]: v });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.addExam(patientId, {
        exam_type: f.exam_type, result: f.result, conclusion: f.conclusion || null,
        exam_date: f.exam_date || null, source: f.source || null, screening_id: f.screening_id || null,
      });
      onDone();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} style={{ borderBottom: "1px solid var(--border)", paddingBottom: 12, marginBottom: 12 }}>
      <ErrorNotice message={error} />
      <div className="grid grid-2">
        <label className="field"><span className="field-label">Type d'examen</span>
          <select value={f.exam_type} onChange={(e) => set("exam_type", e.target.value)}>
            {Object.entries(EXAM_TYPES).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select></label>
        <label className="field"><span className="field-label">Conclusion</span>
          <select value={f.conclusion} onChange={(e) => set("conclusion", e.target.value)}>
            <option value="">— Non précisée —</option>
            {Object.entries(CONCLUSIONS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select></label>
        <label className="field"><span className="field-label">Date de l'examen</span>
          <input type="date" value={f.exam_date} onChange={(e) => set("exam_date", e.target.value)} /></label>
        <label className="field"><span className="field-label">Source (laboratoire, service)</span>
          <input type="text" value={f.source} onChange={(e) => set("source", e.target.value)} /></label>
      </div>
      {screenings.length > 0 && (
        <label className="field"><span className="field-label">Dépistage concerné</span>
          <select value={f.screening_id} onChange={(e) => set("screening_id", e.target.value)}>
            <option value="">— Aucun —</option>
            {screenings.map((s) => <option key={s.id} value={s.id}>{PATHOLOGY_LABELS[s.pathology]} du {formatDate(s.created_at)}</option>)}
          </select></label>
      )}
      <label className="field"><span className="field-label">Résultat<span className="req">*</span></span>
        <textarea required value={f.result} onChange={(e) => set("result", e.target.value)} placeholder="ex. Nodule ovalaire 12 mm, ACR 3" /></label>
      <button className="btn btn-primary btn-sm" disabled={busy}>Enregistrer le résultat</button>
    </form>
  );
}
