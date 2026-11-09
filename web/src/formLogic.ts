// Logique des formulaires, alignée sur api/app/services/forms.py (le serveur reste la référence).
import type { FieldValue, FormData, FormDef, FormField } from "./api";

export const UNKNOWN = "inconnu";

export function isMissing(v: FieldValue | undefined): boolean {
  return v === null || v === undefined || v === "" || (Array.isArray(v) && v.length === 0);
}

export function isVisible(field: FormField, data: FormData): boolean {
  const cond = field.show_if;
  if (!cond) return true;
  const other = data[cond.field];
  if ("equals" in cond) return other === cond.equals;
  if (cond.greater_than !== undefined) return typeof other === "number" && other > cond.greater_than;
  return true;
}

export function fieldError(field: FormField, v: FieldValue | undefined): string | null {
  if (isMissing(v)) return null;
  switch (field.type) {
    case "integer":
    case "number": {
      if (typeof v !== "number" || Number.isNaN(v)) return "Valeur numérique attendue";
      if (field.type === "integer" && !Number.isInteger(v)) return "Nombre entier attendu";
      if (field.min !== undefined && v < field.min) return `Minimum : ${field.min}`;
      if (field.max !== undefined && v > field.max) return `Maximum : ${field.max}`;
      return null;
    }
    case "choice":
      return field.options?.some((o) => o.value === v) ? null : "Option non reconnue";
    default:
      return null;
  }
}

export function isAlert(field: FormField, v: FieldValue | undefined): boolean {
  if (isMissing(v)) return false;
  if (field.alert_when !== undefined && v === field.alert_when) return true;
  const values = Array.isArray(v) ? v : [v];
  return (field.options ?? []).some((o) => o.alert && values.includes(o.value));
}

export interface FormCheck {
  missing: string[];
  errors: Record<string, string>;
  alerts: { field: string; label: string }[];
  /** Données à envoyer : champs masqués retirés */
  cleaned: FormData;
}

export function checkForm(form: FormDef, data: FormData): FormCheck {
  const result: FormCheck = { missing: [], errors: {}, alerts: [], cleaned: {} };
  for (const section of form.sections) {
    for (const f of section.fields) {
      if (!isVisible(f, data)) continue;
      const v = data[f.id];
      if (isMissing(v)) {
        if (f.required) result.missing.push(f.id);
        continue;
      }
      const err = fieldError(f, v);
      if (err) {
        result.errors[f.id] = err;
        continue;
      }
      result.cleaned[f.id] = v as FieldValue;
      if (isAlert(f, v)) result.alerts.push({ field: f.id, label: f.label });
    }
  }
  return result;
}

/** Libellé lisible d'une valeur saisie (pour l'affichage d'un dossier). */
export function displayValue(field: FormField, v: FieldValue | undefined): string {
  if (isMissing(v)) return "—";
  if (field.type === "boolean") return v === true ? "Oui" : v === false ? "Non" : "Inconnu";
  const label = (x: string) => field.options?.find((o) => o.value === x)?.label ?? x;
  if (Array.isArray(v)) return v.map(label).join(", ");
  if (typeof v === "string" && field.options) return label(v);
  return field.unit ? `${v} ${field.unit}` : String(v);
}

export function fieldIndex(form: FormDef): Record<string, FormField> {
  return Object.fromEntries(form.sections.flatMap((s) => s.fields.map((f) => [f.id, f])));
}
