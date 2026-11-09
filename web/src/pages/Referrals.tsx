import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { ErrorNotice, Loading, PATHOLOGY_LABELS, REFERRAL_LABELS, RiskBadge, formatDate, useAsync } from "../components/ui";

type Tab = "a_valider" | "entrantes" | "programmees" | "a_relancer" | "toutes";

export function Referrals() {
  const { can, user } = useAuth();
  const tabs: [Tab, string][] = [
    ...(can("referrals:decide") ? [["a_valider", "À valider"] as [Tab, string]] : []),
    ...(user?.role === "specialiste" ? [["entrantes", "Référées vers mon établissement"] as [Tab, string]] : []),
    ["programmees", "Rendez-vous programmés"],
    ["a_relancer", "Perdues de vue / à relancer"],
    ["toutes", "Toutes"],
  ];
  const [tab, setTab] = useState<Tab>(tabs[0][0]);

  const query = {
    a_valider: { pending_decision: true },
    entrantes: { direction: "incoming" },
    programmees: { status: "programmee" as const },
    a_relancer: { overdue: true },
    toutes: {},
  }[tab];
  const { data, error, loading } = useAsync(() => api.referrals(query), [tab]);
  const lost = useAsync(() => (tab === "a_relancer" ? api.referrals({ status: "perdue_de_vue" }) : Promise.resolve([])), [tab]);
  const rows = tab === "a_relancer" ? [...(data ?? []), ...(lost.data ?? [])] : data ?? [];

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Orientations et suivi</h1>
          <p className="muted">Les cas à risque élevé apparaissent en premier.</p>
        </div>
      </div>
      <div className="segmented" role="tablist" style={{ marginBottom: 16 }}>
        {tabs.map(([k, label]) => <button key={k} role="tab" aria-selected={tab === k} aria-pressed={tab === k} onClick={() => setTab(k)}>{label}</button>)}
      </div>
      {tab === "a_relancer" && <p className="muted small">Rendez-vous dépassé de plus de 30 jours sans réalisation, ou patientes signalées perdues de vue.</p>}
      <ErrorNotice message={error} />
      {loading ? <Loading /> : (
        <div className="card table-wrap" style={{ padding: 0 }}>
          {rows.length ? (
            <table>
              <thead><tr><th>Patiente</th><th>Pathologie</th><th>Orientation proposée</th><th>Statut</th><th>Rendez-vous</th><th>Créée le</th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td><Link to={`/depistages/${r.screening_id}`}>{r.patient_code}</Link></td>
                    <td>{PATHOLOGY_LABELS[r.pathology]}</td>
                    <td><RiskBadge level={r.proposed_level} /></td>
                    <td>{r.final_decision ? REFERRAL_LABELS[r.status] : <span className="badge badge-warn">À valider</span>}</td>
                    <td>{formatDate(r.appointment_date)}</td>
                    <td>{formatDate(r.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <div className="empty">Aucune orientation dans cette liste.</div>}
        </div>
      )}
    </>
  );
}
