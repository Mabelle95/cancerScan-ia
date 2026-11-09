import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type Patient, type PatientSummary } from "../api";
import { TOGO_REGIONS, patientAge } from "../components/ui";

const EDUCATION = [
  ["aucun", "Aucun"], ["primaire", "Primaire"], ["secondaire", "Secondaire"], ["superieur", "Supérieur"],
] as const;

export function PatientNew() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    full_name: "", phone: "", birth_date: "", birth_year_estimated: "", region: "Maritime", locality: "",
    education_level: "", consent_given: false, consent_research: false,
  });
  const [ageKnown, setAgeKnown] = useState<"date" | "annee">("date");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<{ patient: Patient; duplicates: PatientSummary[] } | null>(null);
  const set = (k: keyof typeof form, v: string | boolean) => setForm({ ...form, [k]: v });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api.createPatient({
        full_name: form.full_name || null,
        phone: form.phone || null,
        birth_date: ageKnown === "date" ? form.birth_date || null : null,
        birth_year_estimated: ageKnown === "annee" && form.birth_year_estimated ? Number(form.birth_year_estimated) : null,
        region: form.region,
        locality: form.locality || null,
        education_level: form.education_level || null,
        consent_given: form.consent_given,
        consent_research: form.consent_research,
      });
      if (res.possible_duplicates.length) setCreated({ patient: res.patient, duplicates: res.possible_duplicates });
      else navigate(`/patients/${res.patient.id}/depistage`, { replace: true });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (created) {
    return (
      <div className="card" style={{ maxWidth: 720 }}>
        <div className="notice notice-warn"><strong>Doublon possible</strong>Le dossier {created.patient.code} a été créé, mais des dossiers similaires existent déjà (même téléphone, ou même nom et même année de naissance).</div>
        <ul>
          {created.duplicates.map((d) => (
            <li key={d.id}><Link to={`/patients/${d.id}`}>{d.code}</Link> — {d.full_name ?? "sans nom"}, {patientAge(d)}, {d.locality ?? d.region}</li>
          ))}
        </ul>
        <div className="row" style={{ marginTop: 12 }}>
          <Link className="btn btn-primary" to={`/patients/${created.patient.id}/depistage`}>Continuer avec le nouveau dossier</Link>
          <Link className="btn" to={`/patients/${created.patient.id}`}>Voir le nouveau dossier</Link>
        </div>
      </div>
    );
  }

  const year = new Date().getFullYear();
  return (
    <form onSubmit={submit} style={{ maxWidth: 720 }}>
      <div className="page-head"><h1>Nouvelle patiente</h1></div>
      {error && <div className="notice notice-danger" role="alert">{error}</div>}

      <div className="card">
        <h2>Consentement</h2>
        <label className="checks" style={{ marginBottom: 10 }}>
          <span className="row"><input type="checkbox" checked={form.consent_given} onChange={(e) => set("consent_given", e.target.checked)} required />
            <strong>La patiente a donné son consentement éclairé</strong> au recueil et au traitement de ses données pour le dépistage.<span className="req" style={{ color: "var(--danger)" }}>*</span></span>
        </label>
        <label className="checks">
          <span className="row"><input type="checkbox" checked={form.consent_research} onChange={(e) => set("consent_research", e.target.checked)} />
            Elle accepte en plus que ses données pseudonymisées servent à la recherche (facultatif).</span>
        </label>
      </div>

      <div className="card">
        <h2>Identification</h2>
        <p className="field-help" style={{ marginTop: -6, marginBottom: 14 }}>Le nom et le téléphone sont chiffrés et ne sont jamais transmis au moteur IA.</p>
        <label className="field"><span className="field-label">Nom complet</span>
          <input type="text" value={form.full_name} onChange={(e) => set("full_name", e.target.value)} maxLength={200} /></label>
        <label className="field"><span className="field-label">Téléphone</span>
          <input type="text" inputMode="tel" placeholder="+228 90 00 00 00" value={form.phone} onChange={(e) => set("phone", e.target.value)} maxLength={30} /></label>

        <span className="field-label">Âge</span>
        <div className="segmented" style={{ marginBottom: 8 }} role="group">
          <button type="button" aria-pressed={ageKnown === "date"} onClick={() => setAgeKnown("date")}>Date de naissance connue</button>
          <button type="button" aria-pressed={ageKnown === "annee"} onClick={() => setAgeKnown("annee")}>Année estimée</button>
        </div>
        {ageKnown === "date" ? (
          <input type="date" value={form.birth_date} max={new Date().toISOString().slice(0, 10)} onChange={(e) => set("birth_date", e.target.value)} style={{ maxWidth: 200, marginBottom: 14 }} aria-label="Date de naissance" />
        ) : (
          <input type="number" placeholder={`ex. ${year - 45}`} min={1900} max={year} value={form.birth_year_estimated}
            onChange={(e) => set("birth_year_estimated", e.target.value)} style={{ maxWidth: 200, marginBottom: 14 }} aria-label="Année de naissance estimée" />
        )}

        <div className="grid grid-2">
          <label className="field"><span className="field-label">Région<span className="req">*</span></span>
            <select value={form.region} onChange={(e) => set("region", e.target.value)}>
              {TOGO_REGIONS.map((r) => <option key={r}>{r}</option>)}
            </select></label>
          <label className="field"><span className="field-label">Localité</span>
            <input type="text" value={form.locality} onChange={(e) => set("locality", e.target.value)} maxLength={150} /></label>
        </div>
        <label className="field"><span className="field-label">Niveau d'éducation</span>
          <select value={form.education_level} onChange={(e) => set("education_level", e.target.value)}>
            <option value="">— Non renseigné —</option>
            {EDUCATION.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select></label>
      </div>

      <div className="row">
        <button className="btn btn-primary" disabled={busy || !form.consent_given}>{busy ? "Enregistrement…" : "Créer le dossier et commencer le dépistage"}</button>
        <Link className="btn" to="/patients">Annuler</Link>
      </div>
    </form>
  );
}
