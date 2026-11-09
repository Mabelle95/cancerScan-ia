import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type FormData, type Pathology, type SubmitResult } from "../api";
import { FormRenderer } from "../components/FormRenderer";
import { ErrorNotice, Loading, PATHOLOGY_LABELS, useAsync } from "../components/ui";
import { PATHOLOGY_ORDER, useForms } from "../components/useForms";
import { checkForm } from "../formLogic";

/** Nouveau dépistage (/patients/:id/depistage) ou reprise d'un brouillon (/depistages/:sid/modifier). */
export function ScreeningForm() {
  const { id, sid } = useParams();
  const navigate = useNavigate();
  const { forms, error: formsError, byPathology } = useForms();
  const existing = useAsync(() => (sid ? api.screening(sid) : Promise.resolve(null)), [sid]);
  const patientId = id ?? existing.data?.patient_id ?? "";
  const patient = useAsync(() => (patientId ? api.patient(patientId) : Promise.resolve(null)), [patientId]);

  const [pathology, setPathology] = useState<Pathology | null>(null);
  const [data, setData] = useState<FormData>({});
  const [showMissing, setShowMissing] = useState(false);
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (existing.data) {
      setPathology(existing.data.pathology);
      setData(existing.data.data);
    }
  }, [existing.data]);

  const form = pathology ? byPathology(pathology) : undefined;
  const check = useMemo(() => (form ? checkForm(form, data) : null), [form, data]);

  if (formsError) return <ErrorNotice message={formsError} />;
  if (!forms || existing.loading || patient.loading) return <Loading />;
  if (existing.error) return <ErrorNotice message={existing.error} />;

  const save = async (submit: boolean) => {
    if (!form || !check) return;
    if (submit && (check.missing.length || Object.keys(check.errors).length)) {
      setShowMissing(true);
      setError("Complétez les champs obligatoires et corrigez les erreurs avant de soumettre.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      let res: SubmitResult;
      if (sid) {
        // Un dépistage déjà soumis est ré-analysé par l'API lors de la modification ; seul un brouillon est soumis.
        res = await api.updateScreening(sid, check.cleaned);
        if (submit && res.screening.status === "brouillon") res = await api.submitScreening(sid);
      } else {
        res = await api.createScreening(patientId, form.pathology, check.cleaned, submit);
      }
      setServerErrors(res.errors);
      if (submit && res.screening.status === "brouillon") {
        setShowMissing(true);
        setError("Le serveur a refusé la soumission : vérifiez les champs signalés.");
        if (!sid) navigate(`/depistages/${res.screening.id}/modifier`, { replace: true });
        return;
      }
      navigate(submit ? `/depistages/${res.screening.id}` : `/patients/${patientId}`, { replace: true });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const header = (
    <div className="page-head">
      <div>
        <p className="muted small" style={{ margin: 0 }}>
          <Link to="/patients">Patientes</Link> / {patient.data && <Link to={`/patients/${patientId}`}>{patient.data.full_name ?? patient.data.code}</Link>} /
        </p>
        <h1>{form ? form.title : "Nouveau dépistage"}</h1>
      </div>
    </div>
  );

  if (!pathology || !form) {
    return (
      <>
        {header}
        <div className="card">
          <h2>Quelle pathologie dépister ?</h2>
          <p className="muted">Chaque pathologie a ses propres facteurs de risque et son propre formulaire.</p>
          <div className="grid grid-4" style={{ marginTop: 12 }}>
            {PATHOLOGY_ORDER.filter((p) => byPathology(p)).map((p) => (
              <button key={p} className={`btn${p === "sein" ? " btn-primary" : ""}`} style={{ minHeight: 64 }} onClick={() => setPathology(p)}>
                {PATHOLOGY_LABELS[p]}{p === "sein" && " — prioritaire"}
              </button>
            ))}
          </div>
        </div>
      </>
    );
  }

  const missing = new Set(showMissing ? check!.missing : []);
  const errors = { ...serverErrors, ...check!.errors };

  return (
    <>
      {header}
      {!form.validated && (
        <div className="notice notice-warn"><strong>Formulaire provisoire (v{form.version})</strong>Son contenu doit être validé par des professionnels de santé avant tout usage clinique.</div>
      )}
      {check!.alerts.length > 0 && (
        <div className="notice notice-danger" role="status">
          <strong>Signe(s) d'alerte relevé(s)</strong>
          {check!.alerts.map((a) => a.label).join(" · ")}. Une évaluation médicale est nécessaire, quel que soit le résultat de l'analyse.
        </div>
      )}
      <ErrorNotice message={error} />
      <FormRenderer form={form} data={data} onChange={setData} errors={errors} missing={missing} />
      <div className="card form-actions" style={{ margin: 0 }}>
        <span className="muted small">
          {check!.missing.length ? `${check!.missing.length} champ(s) obligatoire(s) restant(s)` : "Formulaire complet"}
        </span>
        <span className="spacer" />
        <button className="btn" disabled={busy} onClick={() => save(false)}>Enregistrer le brouillon</button>
        <button className="btn btn-primary" disabled={busy} onClick={() => save(true)}>{busy ? "Analyse…" : "Soumettre pour analyse"}</button>
      </div>
    </>
  );
}
