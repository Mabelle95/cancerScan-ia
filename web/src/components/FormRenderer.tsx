import type { FieldValue, FormData, FormDef, FormField } from "../api";
import { UNKNOWN, isAlert, isVisible } from "../formLogic";
import { Icon, SECTION_ICONS } from "./Icon";

interface Props {
  form: FormDef;
  data: FormData;
  onChange: (data: FormData) => void;
  errors: Record<string, string>;
  /** Champs obligatoires manquants à signaler (après une tentative de soumission) */
  missing: Set<string>;
}

/** Libellés courts des étapes : identiques à l'assistant de l'application mobile (theme.dart › stepLabel). */
const STEP_LABELS: Record<string, string> = {
  antecedents: "Identité", symptomes: "Symptômes", examen_clinique: "Examen",
  donnees_complementaires: "Infos", orientation: "Validation", facteurs_risque: "Risques",
};

export function FormRenderer({ form, data, onChange, errors, missing }: Props) {
  const set = (id: string, value: FieldValue) => onChange({ ...data, [id]: value });
  // Sections ayant au moins une question posée pendant la saisie (pas uniquement « après résultat »)
  const sections = form.sections.filter((s) => s.fields.some((f) => !f.after_result));
  const total = sections.length;

  return (
    <div>
      <nav className="stepper" aria-label="Étapes du formulaire">
        {sections.map((s, i) => (
          <a key={s.id} href={`#section-${s.id}`}><span className="num">{i + 1}</span>{STEP_LABELS[s.id] ?? s.title}</a>
        ))}
      </nav>
      {sections.map((section, i) => {
        // Les questions « après résultat » (appréciation de l'agent) ne sont pas posées avant l'analyse
        const visible = section.fields.filter((f) => !f.after_result && isVisible(f, data));
        if (!visible.length) return null;
        const icon = SECTION_ICONS[section.icon ?? ""] ?? "note";
        return (
          <section key={section.id} id={`section-${section.id}`} className="card" style={{ scrollMarginTop: 16 }}>
            <div className="section-head">
              <span className="icon-tile"><Icon name={icon} size={28} /></span>
              <div>
                <div className="eyebrow">Étape {i + 1} sur {total}</div>
                <h2>{section.title}</h2>
              </div>
            </div>
            {visible.map((f) => (
              <Field key={f.id} field={f} value={data[f.id] ?? null} onChange={(v) => set(f.id, v)}
                error={errors[f.id] ?? (missing.has(f.id) ? "Réponse obligatoire (choisissez NSP si la patiente ne sait pas)" : undefined)} />
            ))}
          </section>
        );
      })}
    </div>
  );
}

export function Field({ field, value, onChange, error }: { field: FormField; value: FieldValue; onChange: (v: FieldValue) => void; error?: string }) {
  const alert = isAlert(field, value);
  const labelId = `lbl-${field.id}`;
  const labelText = (
    <span className={`field-label${alert ? " alert-label" : ""}`} id={labelId}>
      {field.label}{field.unit ? ` (${field.unit})` : ""}
      {field.required && <span className="req" aria-label="obligatoire">*</span>}
      {alert && <span className="badge badge-alert" style={{ marginLeft: 8 }}>Signe d'alerte</span>}
    </span>
  );

  let body: JSX.Element;
  switch (field.type) {
    case "boolean":
      // Une ligne : la question à gauche, Oui / Non / NSP à droite — comme sur le mobile
      body = (
        <div className="question-row">
          {labelText}
          <div className="segmented" role="group" aria-labelledby={labelId}>
            {([[true, "Oui", field.alert_when === true ? "alert-on" : ""], [false, "Non", ""], [UNKNOWN, "NSP", "unknown"]] as const).map(([v, text, cls]) => (
              <button type="button" key={text} aria-pressed={value === v} className={cls || undefined}
                title={text === "NSP" ? "Ne sait pas" : undefined} onClick={() => onChange(value === v ? null : v)}>{text}</button>
            ))}
          </div>
        </div>
      );
      break;
    case "choice": {
      const short = (field.options?.length ?? 0) <= 3 && field.options!.every((o) => o.label.length <= 14);
      body = (
        <>
          {labelText}
          {short ? (
            <div className="chips" role="group" aria-labelledby={labelId}>
              {field.options!.map((o) => (
                <button type="button" key={o.value} className={`chip${o.alert ? " alert-on" : ""}`} aria-pressed={value === o.value}
                  onClick={() => onChange(value === o.value ? null : o.value)}>{o.label}</button>
              ))}
            </div>
          ) : (
            <select aria-labelledby={labelId} value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value || null)}>
              <option value="">— Non renseigné —</option>
              {field.options!.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          )}
        </>
      );
      break;
    }
    case "multichoice": {
      const current = Array.isArray(value) ? value : [];
      body = (
        <>
          {labelText}
          <div className="chips" role="group" aria-labelledby={labelId}>
            {field.options!.map((o) => (
              <button type="button" key={o.value} className="chip" aria-pressed={current.includes(o.value)}
                onClick={() => onChange(current.includes(o.value) ? current.filter((x) => x !== o.value) : [...current, o.value])}>{o.label}</button>
            ))}
          </div>
        </>
      );
      break;
    }
    case "integer":
    case "number":
      body = (
        <>
          {labelText}
          <input type="number" aria-labelledby={labelId} inputMode={field.type === "integer" ? "numeric" : "decimal"}
            min={field.min} max={field.max} step={field.type === "integer" ? 1 : "any"} style={{ maxWidth: 220 }}
            value={typeof value === "number" ? value : ""}
            onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))} />
          {field.min !== undefined && field.max !== undefined && <div className="field-help">De {field.min} à {field.max}</div>}
        </>
      );
      break;
    case "date":
      body = <>{labelText}<input type="date" aria-labelledby={labelId} value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value || null)} style={{ maxWidth: 220 }} /></>;
      break;
    default:
      body = <>{labelText}<textarea aria-labelledby={labelId} value={(value as string) ?? ""} maxLength={5000} onChange={(e) => onChange(e.target.value || null)} /></>;
  }

  return (
    <div className={`field${error ? " invalid" : ""}`} style={{ marginBottom: 18 }}>
      {body}
      {field.help && <div className="field-help">{field.help}</div>}
      {error && <div className="field-error">{error}</div>}
    </div>
  );
}
