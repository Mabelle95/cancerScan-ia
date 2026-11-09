import type { FieldValue, FormData, FormDef, FormField } from "../api";
import { UNKNOWN, isAlert, isVisible } from "../formLogic";

interface Props {
  form: FormDef;
  data: FormData;
  onChange: (data: FormData) => void;
  errors: Record<string, string>;
  /** Champs obligatoires manquants à signaler (après une tentative de soumission) */
  missing: Set<string>;
}

export function FormRenderer({ form, data, onChange, errors, missing }: Props) {
  const set = (id: string, value: FieldValue) => onChange({ ...data, [id]: value });

  return (
    <div>
      <nav className="section-nav" aria-label="Sections du formulaire">
        {form.sections.map((s) => <a key={s.id} href={`#section-${s.id}`}>{s.title}</a>)}
      </nav>
      {form.sections.map((section) => {
        const visible = section.fields.filter((f) => isVisible(f, data));
        return (
          <fieldset key={section.id} id={`section-${section.id}`} className="card" style={{ border: "1px solid var(--border)" }}>
            <legend style={{ fontWeight: 700, fontSize: "1.05rem", padding: "0 6px" }}>{section.title}</legend>
            {visible.map((f) => (
              <Field key={f.id} field={f} value={data[f.id] ?? null} onChange={(v) => set(f.id, v)}
                error={errors[f.id] ?? (missing.has(f.id) ? "Champ obligatoire" : undefined)} />
            ))}
          </fieldset>
        );
      })}
    </div>
  );
}

function Field({ field, value, onChange, error }: { field: FormField; value: FieldValue; onChange: (v: FieldValue) => void; error?: string }) {
  const alert = isAlert(field, value);
  const labelId = `lbl-${field.id}`;
  const label = (
    <span className="field-label" id={labelId}>
      {field.label}{field.unit ? ` (${field.unit})` : ""}
      {field.required && <span className="req" aria-label="obligatoire">*</span>}
      {alert && <span className="badge badge-alert" style={{ marginLeft: 8 }}>Signe d'alerte</span>}
    </span>
  );

  let control: JSX.Element;
  switch (field.type) {
    case "boolean":
      control = (
        <div className="segmented" role="group" aria-labelledby={labelId}>
          {([[true, "Oui"], [false, "Non"], [UNKNOWN, "Inconnu"]] as const).map(([v, text]) => (
            <button type="button" key={text} aria-pressed={value === v}
              className={field.alert_when === v ? "alert-on" : undefined}
              onClick={() => onChange(value === v ? null : v)}>{text}</button>
          ))}
        </div>
      );
      break;
    case "choice":
      control = (field.options?.length ?? 0) <= 4 ? (
        <div className="segmented" role="group" aria-labelledby={labelId}>
          {field.options!.map((o) => (
            <button type="button" key={o.value} aria-pressed={value === o.value} className={o.alert ? "alert-on" : undefined}
              onClick={() => onChange(value === o.value ? null : o.value)}>{o.label}</button>
          ))}
        </div>
      ) : (
        <select aria-labelledby={labelId} value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value || null)}>
          <option value="">— Non renseigné —</option>
          {field.options!.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      );
      break;
    case "multichoice": {
      const current = Array.isArray(value) ? value : [];
      control = (
        <div className="checks" role="group" aria-labelledby={labelId}>
          {field.options!.map((o) => (
            <label key={o.value}>
              <input type="checkbox" checked={current.includes(o.value)}
                onChange={(e) => onChange(e.target.checked ? [...current, o.value] : current.filter((x) => x !== o.value))} />
              {o.label}
            </label>
          ))}
        </div>
      );
      break;
    }
    case "integer":
    case "number":
      control = (
        <input type="number" aria-labelledby={labelId} inputMode={field.type === "integer" ? "numeric" : "decimal"}
          min={field.min} max={field.max} step={field.type === "integer" ? 1 : "any"} style={{ maxWidth: 180 }}
          value={typeof value === "number" ? value : ""}
          onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))} />
      );
      break;
    case "date":
      control = <input type="date" aria-labelledby={labelId} value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value || null)} style={{ maxWidth: 200 }} />;
      break;
    default:
      control = <textarea aria-labelledby={labelId} value={(value as string) ?? ""} maxLength={5000} onChange={(e) => onChange(e.target.value || null)} />;
  }

  return (
    <div className={`field${error ? " invalid" : ""}`} style={{ marginBottom: 16 }}>
      {label}
      {control}
      {field.help && <div className="field-help">{field.help}</div>}
      {error && <div className="field-error">{error}</div>}
    </div>
  );
}
