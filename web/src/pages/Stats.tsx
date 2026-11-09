import { useState } from "react";
import { api } from "../api";
import { Bars, Card, Donut, ErrorNotice, Loading, PATHOLOGY_LABELS, REFERRAL_LABELS, RISK_COLOR, SHORT_RISK, StatTile, TOGO_REGIONS, useAsync } from "../components/ui";

/** Même graphique en anneau + légende que le tableau de bord mobile. Les effectifs masqués (< seuil) comptent pour 0. */
function RiskDonut({ data, minCell }: { data: Record<string, number | null>; minCell: number }) {
  const levels: [string, string, string][] = [
    ["eleve", SHORT_RISK.eleve, RISK_COLOR.eleve], ["moyen", SHORT_RISK.moyen, RISK_COLOR.moyen],
    ["faible", SHORT_RISK.faible, RISK_COLOR.faible], ["en_attente", "En attente", RISK_COLOR.none],
  ];
  const total = levels.reduce((a, [k]) => a + (data[k] ?? 0), 0);
  return (
    <div className="row" style={{ gap: 24, alignItems: "center", flexWrap: "nowrap" }}>
      <Donut segments={levels.map(([k, , c]) => [data[k] ?? 0, c])}
        center={<div><div style={{ fontSize: "1.7rem", fontWeight: 800 }}>{total}</div><div className="small muted">au total</div></div>} />
      <div style={{ flex: 1 }}>
        {levels.map(([k, label, color]) => (
          <div key={k} className="row" style={{ justifyContent: "space-between", padding: "6px 0", flexWrap: "nowrap" }}>
            <span className="row" style={{ flexWrap: "nowrap" }}><span style={{ width: 12, height: 12, borderRadius: 4, background: color }} />{label}</span>
            <strong>{data[k] === null ? `< ${minCell}` : data[k] ?? 0}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

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
          <div className="grid grid-3" style={{ marginBottom: 18 }}>
            <StatTile value={data.totals.patientes} label="Patientes dépistées" icon="people" color="var(--primary)" />
            <StatTile value={data.totals.depistages} label="Dépistages" icon="note" color="var(--teal)" />
            <StatTile value={data.totals.avec_signes_alerte} label="Avec signes d'alerte" icon="warning" color="var(--risk-eleve)" />
            <StatTile value={data.totals.references} label="Patientes référées" icon="route" color="var(--violet)" />
            <StatTile value={data.totals.taux_realisation === null ? "—" : `${Math.round(data.totals.taux_realisation * 100)} %`}
              label="Références réalisées" icon="check" color="var(--risk-faible)" />
            <StatTile value={data.totals.delai_median_jours === null ? "—" : `${data.totals.delai_median_jours} j`}
              label="Délai médian dépistage → consultation" icon="hourglass" color="var(--risk-moyen)" />
          </div>
          <div className="grid grid-2">
            <Card title="Répartition des risques estimés" icon="donut">
              <RiskDonut data={data.par_niveau_risque} minCell={data.min_cell_size} />
            </Card>
            <Card title="Par région" icon="route"><Bars data={data.par_region} minCell={data.min_cell_size} /></Card>
            <Card title="Par tranche d'âge" icon="people"><Bars data={data.par_tranche_age} minCell={data.min_cell_size} /></Card>
            <Card title="Par pathologie" icon="medical"><Bars data={data.par_pathologie} minCell={data.min_cell_size} labels={PATHOLOGY_LABELS} /></Card>
            <Card title="Suivi des références" icon="list"><Bars data={data.statut_references} minCell={data.min_cell_size} labels={REFERRAL_LABELS} /></Card>
            <Card title="Cas confirmés par les examens de référence" icon="check" iconColor="var(--risk-eleve)">
              <Bars data={data.totals.cas_confirmes} minCell={data.min_cell_size} labels={{ malin: "Malin", precancereux: "Précancéreux" }} />
            </Card>
          </div>
          <Card title="Évolution mensuelle des dépistages" icon="chart" iconColor="var(--violet)"><Bars data={data.evolution_mensuelle} minCell={data.min_cell_size} /></Card>
        </>
      )}
    </>
  );
}
