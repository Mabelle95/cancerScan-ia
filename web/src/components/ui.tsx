import { useCallback, useEffect, useState, type ReactNode } from "react";
import type { Explanation, PatientSummary, RiskLevel, ScreeningStatus, ReferralStatus } from "../api";
import { Icon } from "./Icon";

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

/** Mêmes libellés courts, icônes et couleurs que l'application mobile (riskStyle / shortRiskLabel). */
export const SHORT_RISK: Record<RiskLevel, string> = { faible: "Faible", moyen: "Moyen", eleve: "Élevé" };
export const RISK_ICON: Record<RiskLevel | "none", string> = { faible: "check", moyen: "warning", eleve: "priority", none: "hourglass" };
export const RISK_COLOR: Record<RiskLevel | "none", string> = {
  faible: "var(--risk-faible)", moyen: "var(--risk-moyen)", eleve: "var(--risk-eleve)", none: "var(--risk-none)",
};

export function RiskBadge({ level, large, compact }: { level: RiskLevel | null | undefined; large?: boolean; compact?: boolean }) {
  const key = level ?? "none";
  const label = level ? (compact ? SHORT_RISK[level] : RISK_LABELS[level]) : (compact ? "En attente" : "Analyse en attente");
  return (
    <span className={`risk risk-${key}${large ? " risk-lg" : ""}`}>
      <Icon name={RISK_ICON[key]} size={large ? 18 : 15} />{label}
    </span>
  );
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

/** Carte à ombre douce avec en-tête icône + titre (comme InfoCard du mobile). */
export function Card({ title, actions, icon, iconColor, children }: { title?: ReactNode; actions?: ReactNode; icon?: string; iconColor?: string; children: ReactNode }) {
  return (
    <section className="card">
      {(title || actions) && (
        <div className="card-title">
          {icon && (
            <span className="icon-badge" style={iconColor ? { color: iconColor, background: `color-mix(in srgb, ${iconColor} 13%, transparent)` } : undefined}>
              <Icon name={icon} size={22} />
            </span>
          )}
          {title && <h2>{title}</h2>}
          <span className="spacer" />
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

/** Tuile chiffrée (même composant que StatTile du mobile). */
export function StatTile({ value, label, icon, color }: { value: ReactNode; label: string; icon: string; color: string }) {
  return (
    <div className="card stat" style={{ marginBottom: 0 }}>
      <span className="stat-icon" style={{ color, background: `color-mix(in srgb, ${color} 13%, transparent)` }}><Icon name={icon} size={20} /></span>
      <span className="stat-value" style={{ color }}>{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  );
}

/** Anneau de score animé (même rendu que ScoreRing du mobile). */
export function ScoreRing({ score, size = 156 }: { score: number; size?: number }) {
  const [shown, setShown] = useState(0);
  useEffect(() => {
    const t = requestAnimationFrame(() => setShown(Math.max(0, Math.min(1, score))));
    return () => cancelAnimationFrame(t);
  }, [score]);
  const stroke = size * 0.085, r = (size - stroke) / 2, c = 2 * Math.PI * r;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`Score estimé ${Math.round(score * 100)} %`}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.25)" strokeWidth={stroke} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#fff" strokeWidth={stroke} strokeLinecap="round"
        strokeDasharray={c} strokeDashoffset={c * (1 - shown)} transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: "stroke-dashoffset 1.1s cubic-bezier(.2,.8,.2,1)" }} />
      <text x="50%" y="48%" textAnchor="middle" fill="#fff" fontSize={size * 0.22} fontWeight={800}>{Math.round(score * 100)} %</text>
      <text x="50%" y="64%" textAnchor="middle" fill="rgba(255,255,255,0.8)" fontSize={size * 0.08}>score estimé</text>
    </svg>
  );
}

/** Graphique en anneau (même rendu que DonutChart du mobile). */
export function Donut({ segments, size = 150, center }: { segments: [number, string][]; size?: number; center?: ReactNode }) {
  const stroke = size * 0.16, r = (size - stroke) / 2, c = 2 * Math.PI * r;
  const total = segments.reduce((a, [v]) => a + v, 0);
  let offset = 0;
  return (
    <div style={{ position: "relative", width: size, height: size, flex: "none" }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--border)" strokeWidth={stroke} />
        {total > 0 && segments.map(([v, color], i) => {
          if (v <= 0) return null;
          const len = (v / total) * c;
          const el = <circle key={i} cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
            strokeDasharray={`${Math.max(len - 3, 0)} ${c}`} strokeDashoffset={-offset} transform={`rotate(-90 ${size / 2} ${size / 2})`} />;
          offset += len;
          return el;
        })}
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", textAlign: "center" }}>{center}</div>
    </div>
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
