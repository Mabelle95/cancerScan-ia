import { useCallback, useEffect, useState, type ReactNode } from "react";
import type { Explanation, PatientSummary, RiskLevel, ScreeningStatus, ReferralStatus } from "../api";

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(fn, deps);
  const reload = useCallback(() => {
    setLoading(true);
    setError(null);
    load().then(setData).catch((e: Error) => setError(e.message)).finally(() => setLoading(false));
  }, [load]);
  useEffect(reload, [reload]);
  return { data, error, loading, reload, setData };
}

export function Loading() {
  return <div className="spinner" role="status">Chargement…</div>;
}

export function ErrorNotice({ message }: { message: string | null }) {
  if (!message) return null;
  return <div className="notice notice-danger" role="alert">{message}</div>;
}

export const RISK_LABELS: Record<RiskLevel, string> = { faible: "Risque faible", moyen: "Risque moyen", eleve: "Risque élevé" };
export const PATHOLOGY_LABELS: Record<string, string> = { sein: "Sein", col: "Col de l'utérus", ovaire: "Ovaire", endometre: "Endomètre" };
export const STATUS_LABELS: Record<ScreeningStatus, string> = {
  brouillon: "Brouillon", soumis: "Analyse IA en attente", analyse: "Analysé — à valider", valide: "Orientation validée",
};
export const REFERRAL_LABELS: Record<ReferralStatus, string> = {
  proposee: "Proposée", programmee: "Programmée", realisee: "Réalisée", perdue_de_vue: "Perdue de vue", annulee: "Annulée",
};

export function RiskBadge({ level, large }: { level: RiskLevel | null | undefined; large?: boolean }) {
  const cls = `risk risk-${level ?? "none"}${large ? " risk-lg" : ""}`;
  return <span className={cls}>{level ? RISK_LABELS[level] : "Non calculé"}</span>;
}

export function StatusBadge({ status }: { status: ScreeningStatus }) {
  const cls = status === "valide" ? "badge badge-ok" : status === "soumis" ? "badge badge-warn" : "badge";
  return <span className={cls}>{STATUS_LABELS[status]}</span>;
}

/** Contributions SHAP : à droite ce qui augmente l'estimation, à gauche ce qui la diminue. */
/** La réponse saisie est affichée avec chaque facteur : une contribution ne doit jamais être lue hors contexte. */
export function Explanations({ items, format }: { items: Explanation[]; format?: (feature: string, value: Explanation["value"]) => string }) {
  if (!items.length) return <p className="muted">Aucune explication disponible.</p>;
  const max = Math.max(...items.map((e) => Math.abs(e.contribution)), 1e-6);
  return (
    <div>
      {items.map((e) => {
        const up = e.contribution > 0;
        const width = `${(Math.abs(e.contribution) / max) * 50}%`;
        const answer = "value" in e ? (format ? format(e.feature, e.value ?? null) : String(e.value ?? "non renseigné")) : null;
        return (
          <div className="explain-row" key={e.feature}>
            <span>{e.label ?? e.feature}{answer !== null && <strong> : {answer}</strong>}</span>
            <div className="explain-track" title={`${up ? "Augmente" : "Diminue"} l'estimation (${e.contribution.toFixed(2)})`}>
              <div className={`explain-bar ${up ? "up" : "down"}`} style={{ width }} />
            </div>
          </div>
        );
      })}
      <p className="field-help">
        Rouge : facteur qui augmente l'estimation · vert : facteur qui la diminue. Ces contributions décrivent le
        fonctionnement du modèle ; elles ne prouvent pas une relation de cause à effet.
      </p>
    </div>
  );
}

/** Barres horizontales ; les effectifs masqués (&lt; seuil) sont affichés « &lt; n ». */
export function Bars({ data, labels, minCell, color }: { data: Record<string, number | null>; labels?: Record<string, string>; minCell: number; color?: (k: string) => string }) {
  const entries = Object.entries(data);
  if (!entries.length) return <p className="muted">Aucune donnée.</p>;
  const max = Math.max(...entries.map(([, v]) => v ?? 0), 1);
  return (
    <div>
      {entries.map(([k, v]) => (
        <div className="bar-row" key={k}>
          <span>{labels?.[k] ?? k}</span>
          <div className="bar-track"><div className="bar-fill" style={{ width: `${((v ?? 0) / max) * 100}%`, background: color?.(k) }} /></div>
          <span className="bar-value">{v === null ? `< ${minCell}` : v}</span>
        </div>
      ))}
    </div>
  );
}

export function Card({ title, actions, children }: { title?: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="card">
      {(title || actions) && (
        <div className="row" style={{ marginBottom: 12 }}>
          {title && <h2 style={{ margin: 0 }}>{title}</h2>}
          <span className="spacer" />
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function formatDate(iso: string | null | undefined, withTime = false): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return withTime
    ? d.toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })
    : d.toLocaleDateString("fr-FR");
}

export function patientAge(p: Pick<PatientSummary, "birth_date" | "birth_year_estimated">): string {
  const now = new Date();
  if (p.birth_date) {
    const b = new Date(p.birth_date);
    const age = now.getFullYear() - b.getFullYear() - (now < new Date(now.getFullYear(), b.getMonth(), b.getDate()) ? 1 : 0);
    return `${age} ans`;
  }
  if (p.birth_year_estimated) return `~${now.getFullYear() - p.birth_year_estimated} ans`;
  return "Âge inconnu";
}

export const TOGO_REGIONS = ["Maritime", "Plateaux", "Centrale", "Kara", "Savanes"];
