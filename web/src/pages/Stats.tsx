import { useState } from "react";
import { api } from "../api";
import { Bars, Card, ErrorNotice, Loading, PATHOLOGY_LABELS, REFERRAL_LABELS, RISK_LABELS, TOGO_REGIONS, useAsync } from "../components/ui";

const RISK_COLORS: Record<string, string> = {
  faible: "var(--risk-faible)", moyen: "var(--risk-moyen)", eleve: "var(--risk-eleve)", en_attente: "var(--text-muted)",
};

export function Stats() {
  const [filters, setFilters] = useState({ region: "", pathology: "", date_from: "", date_to: "" });
  const { data, error, loading } = useAsync(() => api.stats(filters), [JSON.stringify(filters)]);
  const set = (k: keyof typeof filters, v: string) => setFilters({ ...filters, [k]: v });

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Statistiques</h1>
          <p className="muted">
            Données agrégées{data?.scope === "etablissement" ? " de votre établissement" : " nationales"}.
            {data && ` Les effectifs inférieurs à ${data.min_cell_size} sont masqués pour protéger la confidentialité.`}
          </p>
        </div>
      </div>

      <div className="card grid grid-4">
        <label className="field"><span className="field-label">Région</span>
          <select value={filters.region} onChange={(e) => set("region", e.target.value)}>
            <option value="">Toutes</option>{TOGO_REGIONS.map((r) => <option key={r}>{r}</option>)}
          </select></label>
        <label className="field"><span className="field-label">Pathologie</span>
          <select value={filters.pathology} onChange={(e) => set("pathology", e.target.value)}>
            <option value="">Toutes</option>{Object.entries(PATHOLOGY_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select></label>
        <label className="field"><span className="field-label">Du</span><input type="date" value={filters.date_from} onChange={(e) => set("date_from", e.target.value)} /></label>
        <label className="field"><span className="field-label">Au</span><input type="date" value={filters.date_to} onChange={(e) => set("date_to", e.target.value)} /></label>
      </div>

      <ErrorNotice message={error} />
      {loading || !data ? <Loading /> : (
        <>
          <div className="grid grid-4" style={{ marginBottom: 16 }}>
            {[
              ["Patientes dépistées", data.totals.patientes],
              ["Dépistages", data.totals.depistages],
              ["Avec signes d'alerte", data.totals.avec_signes_alerte],
              ["Patientes référées", data.totals.references],
              ["Références réalisées", data.totals.taux_realisation === null ? "—" : `${Math.round(data.totals.taux_realisation * 100)} %`],
              ["Délai médian dépistage → consultation", data.totals.delai_median_jours === null ? "—" : `${data.totals.delai_median_jours} j`],
            ].map(([label, value]) => (
              <div className="card stat" key={label as string} style={{ marginBottom: 0 }}>
                <span className="stat-value">{value}</span><span className="stat-label">{label}</span>
              </div>
            ))}
          </div>
          <div className="grid grid-2">
            <Card title="Répartition des risques estimés">
              <Bars data={data.par_niveau_risque} minCell={data.min_cell_size}
                labels={{ ...RISK_LABELS, en_attente: "Analyse en attente" }} color={(k) => RISK_COLORS[k]} />
            </Card>
            <Card title="Par région"><Bars data={data.par_region} minCell={data.min_cell_size} /></Card>
            <Card title="Par tranche d'âge"><Bars data={data.par_tranche_age} minCell={data.min_cell_size} /></Card>
            <Card title="Par pathologie"><Bars data={data.par_pathologie} minCell={data.min_cell_size} labels={PATHOLOGY_LABELS} /></Card>
            <Card title="Suivi des références"><Bars data={data.statut_references} minCell={data.min_cell_size} labels={REFERRAL_LABELS} /></Card>
            <Card title="Cas confirmés par les examens de référence">
              <Bars data={data.totals.cas_confirmes} minCell={data.min_cell_size} labels={{ malin: "Malin", precancereux: "Précancéreux" }} />
            </Card>
          </div>
          <Card title="Évolution mensuelle des dépistages"><Bars data={data.evolution_mensuelle} minCell={data.min_cell_size} /></Card>
        </>
      )}
    </>
  );
}
