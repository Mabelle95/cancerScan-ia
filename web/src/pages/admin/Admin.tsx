import { Fragment, useState, type FormEvent } from "react";
import { api, type Facility, type Role, type User } from "../../api";
import { ROLE_LABELS, useAuth } from "../../auth";
import { Card, ErrorNotice, Loading, PATHOLOGY_LABELS, TOGO_REGIONS, formatDate, useAsync } from "../../components/ui";

// --- Utilisateurs ---------------------------------------------------------------

export function Users() {
  const { user: me } = useAuth();
  const users = useAsync(() => api.users(), []);
  const facilities = useAsync(() => api.facilities(false), []);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const facilityName = (id: number | null) => facilities.data?.find((f) => f.id === id)?.name ?? "—";

  const isLocked = (u: User) => !!u.locked_until && new Date(u.locked_until) > new Date();
  const unlock = async (u: User) => {
    setError(null);
    try { await api.unlockUser(u.id); users.reload(); } catch (e) { setError((e as Error).message); }
  };

  const toggle = async (u: User) => {
    setError(null);
    try { await api.updateUser(u.id, { is_active: !u.is_active }); users.reload(); } catch (e) { setError((e as Error).message); }
  };

  return (
    <>
      <div className="page-head">
        <h1>Utilisateurs</h1>
        <button className="btn btn-primary" onClick={() => setCreating(!creating)}>{creating ? "Fermer" : "Nouvel utilisateur"}</button>
      </div>
      {creating && <UserForm facilities={facilities.data ?? []} onDone={() => { setCreating(false); users.reload(); }} />}
      <ErrorNotice message={error ?? users.error} />
      {users.loading ? <Loading /> : (
        <div className="card table-wrap" style={{ padding: 0 }}>
          <table>
            <thead><tr><th>Nom</th><th>Rôle</th><th>Établissement</th><th>Dernière connexion</th><th>Statut</th><th /></tr></thead>
            <tbody>
              {users.data?.map((u) => (
                <tr key={u.id}>
                  <td><strong>{u.full_name}</strong><div className="small muted">{u.email}</div></td>
                  <td>{ROLE_LABELS[u.role]}</td>
                  <td>{facilityName(u.facility_id)}</td>
                  <td>{formatDate(u.last_login_at, true)}</td>
                  <td>
                    {isLocked(u)
                      ? <span className="badge badge-alert" title={`Jusqu'à ${formatDate(u.locked_until, true)}`}>Bloqué (échecs de connexion)</span>
                      : u.is_active ? <span className="badge badge-ok">Actif</span> : <span className="badge">Désactivé</span>}
                  </td>
                  <td>
                    <div className="row">
                      {isLocked(u) && <button className="btn btn-sm" onClick={() => unlock(u)}>Débloquer</button>}
                      {u.id !== me?.id && <button className="btn btn-sm" onClick={() => toggle(u)}>{u.is_active ? "Désactiver" : "Réactiver"}</button>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="field-help">Les comptes sont désactivés plutôt que supprimés, pour conserver la traçabilité du journal d'activité.</p>
    </>
  );
}

function UserForm({ facilities, onDone }: { facilities: Facility[]; onDone: () => void }) {
  const [f, setF] = useState({ full_name: "", email: "", role: "agent_sante" as Role, facility_id: "", password: "" });
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof f, v: string) => setF({ ...f, [k]: v });
  const needsFacility = f.role !== "admin" && f.role !== "responsable_sanitaire";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api.createUser({ ...f, facility_id: needsFacility && f.facility_id ? Number(f.facility_id) : null });
      onDone();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <form className="card" onSubmit={submit}>
      <h2>Nouvel utilisateur</h2>
      <ErrorNotice message={error} />
      <div className="grid grid-2">
        <label className="field"><span className="field-label">Nom complet</span><input type="text" required value={f.full_name} onChange={(e) => set("full_name", e.target.value)} /></label>
        <label className="field"><span className="field-label">E-mail</span><input type="email" required value={f.email} onChange={(e) => set("email", e.target.value)} /></label>
        <label className="field"><span className="field-label">Rôle</span>
          <select value={f.role} onChange={(e) => set("role", e.target.value)}>
            {Object.entries(ROLE_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select></label>
        {needsFacility && (
          <label className="field"><span className="field-label">Établissement</span>
            <select required value={f.facility_id} onChange={(e) => set("facility_id", e.target.value)}>
              <option value="">— Choisir —</option>
              {facilities.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
            </select></label>
        )}
        <label className="field"><span className="field-label">Mot de passe initial</span>
          <input type="password" required minLength={10} autoComplete="new-password" value={f.password} onChange={(e) => set("password", e.target.value)} />
          <span className="field-help">10 caractères minimum, avec des lettres et des chiffres, sans l'identifiant.</span></label>
      </div>
      <button className="btn btn-primary">Créer le compte</button>
    </form>
  );
}

// --- Établissements ----------------------------------------------------------------

// Les coordonnées restent du texte pendant la saisie (sinon « 6. » ou « - » seraient effacés à la frappe)
type FacilityDraft = Omit<Facility, "id" | "latitude" | "longitude"> & { id?: number; latitude: string; longitude: string };

const EMPTY_FACILITY: FacilityDraft = {
  code: "", name: "", region: "Maritime", district: "", level: "", is_active: true,
  latitude: "", longitude: "", address: "", phone: "", services: [],
};

/** Texte saisi → nombre ; null si vide ; undefined si invalide ou hors bornes. */
export function parseCoord(text: string, max: number): number | null | undefined {
  const t = text.trim().replace(",", ".");
  if (t === "") return null;
  if (!/^-?\d+(\.\d+)?$/.test(t)) return undefined;
  const n = Number(t);
  return Math.abs(n) <= max ? n : undefined;
}

export function Facilities() {
  const list = useAsync(() => api.facilities(false), []);
  const [editing, setEditing] = useState<FacilityDraft | null>(null);
  const [error, setError] = useState<string | null>(null);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (!editing) return;
    const { id, latitude: latText, longitude: lonText, ...rest } = editing;
    const latitude = parseCoord(latText, 90), longitude = parseCoord(lonText, 180);
    if (latitude === undefined || longitude === undefined) {
      setError("Coordonnées GPS invalides : utilisez des degrés décimaux, par exemple 6.1319 et 1.2228.");
      return;
    }
    if ((latitude === null) !== (longitude === null)) {
      setError("Renseignez la latitude et la longitude, ou aucune des deux.");
      return;
    }
    const body = { ...rest, latitude, longitude };
    try {
      if (id) await api.updateFacility(id, body); else await api.createFacility(body);
      setEditing(null);
      list.reload();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const set = (k: string, v: string | boolean | number | null | string[]) => setEditing(editing && { ...editing, [k]: v });
  const services = useAsync(() => api.facilityServices(), []);
  const toggleService = (s: string) =>
    editing && set("services", editing.services.includes(s) ? editing.services.filter((x) => x !== s) : [...editing.services, s]);

  return (
    <>
      <div className="page-head">
        <h1>Établissements sanitaires</h1>
        <button className="btn btn-primary" onClick={() => setEditing({ ...EMPTY_FACILITY })}>Nouvel établissement</button>
      </div>
      {editing && (
        <form className="card" onSubmit={save}>
          <h2>{editing.id ? "Modifier" : "Nouvel établissement"}</h2>
          <ErrorNotice message={error} />
          <div className="grid grid-2">
            <label className="field"><span className="field-label">Code</span><input type="text" required maxLength={32} value={editing.code} onChange={(e) => set("code", e.target.value.toUpperCase())} /></label>
            <label className="field"><span className="field-label">Nom</span><input type="text" required value={editing.name} onChange={(e) => set("name", e.target.value)} /></label>
            <label className="field"><span className="field-label">Région</span>
              <select value={editing.region} onChange={(e) => set("region", e.target.value)}>{TOGO_REGIONS.map((r) => <option key={r}>{r}</option>)}</select></label>
            <label className="field"><span className="field-label">District</span><input type="text" value={editing.district ?? ""} onChange={(e) => set("district", e.target.value)} /></label>
            <label className="field"><span className="field-label">Niveau</span>
              <select value={editing.level ?? ""} onChange={(e) => set("level", e.target.value)}>
                <option value="">—</option>{["USP", "CMS", "CHP", "CHR", "CHU"].map((l) => <option key={l}>{l}</option>)}
              </select></label>
            <label className="field"><span className="field-label">Téléphone</span><input type="tel" value={editing.phone ?? ""} onChange={(e) => set("phone", e.target.value)} /></label>
            <label className="field"><span className="field-label">Adresse</span><input type="text" value={editing.address ?? ""} onChange={(e) => set("address", e.target.value)} /></label>
            <label className="field"><span className="field-label">Latitude</span><input type="text" inputMode="decimal" placeholder="ex. 6.1319" value={editing.latitude} onChange={(e) => set("latitude", e.target.value)} /></label>
            <label className="field"><span className="field-label">Longitude</span><input type="text" inputMode="decimal" placeholder="ex. 1.2228" value={editing.longitude} onChange={(e) => set("longitude", e.target.value)} />
              <span className="field-help">Position GPS : sert à proposer la structure spécialisée la plus proche des patientes.</span></label>
            <label className="field checks"><span className="row"><input type="checkbox" checked={editing.is_active} onChange={(e) => set("is_active", e.target.checked)} /> Actif</span></label>
          </div>
          <div className="field">
            <span className="field-label">Services spécialisés proposés</span>
            <div className="chips">
              {Object.entries(services.data ?? {}).map(([key, label]) => (
                <button key={key} type="button" className="chip" aria-pressed={editing.services.includes(key)} onClick={() => toggleService(key)}>{label}</button>
              ))}
            </div>
            <span className="field-help">Une structure n'est proposée pour l'orientation que si elle offre une consultation spécialisée. Tenez cette liste à jour.</span>
          </div>
          <div className="row"><button className="btn btn-primary">Enregistrer</button><button type="button" className="btn" onClick={() => setEditing(null)}>Annuler</button></div>
        </form>
      )}
      {list.loading ? <Loading /> : (
        <div className="card table-wrap" style={{ padding: 0 }}>
          <table>
            <thead><tr><th>Code</th><th>Nom</th><th>Région</th><th>Niveau</th><th>Spécialités</th><th>Statut</th><th /></tr></thead>
            <tbody>
              {list.data?.map((f) => (
                <tr key={f.id}>
                  <td>{f.code}</td><td>{f.name}</td><td>{f.region}{f.district ? ` — ${f.district}` : ""}</td><td>{f.level ?? "—"}</td>
                  <td>{f.services?.length ? f.services.length : <span className="muted">—</span>}{f.latitude === null ? <span className="badge badge-warn" style={{ marginLeft: 6 }}>sans GPS</span> : null}</td>
                  <td>{f.is_active ? <span className="badge badge-ok">Actif</span> : <span className="badge">Inactif</span>}</td>
                  <td><button className="btn btn-sm" onClick={() => setEditing({ ...f, services: f.services ?? [], latitude: f.latitude?.toString() ?? "", longitude: f.longitude?.toString() ?? "" })}>Modifier</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

// --- Modèles IA ------------------------------------------------------------------

const pct = (v: number | null) => (v === null ? "—" : `${Math.round(v * 100)} %`);

export function Models() {
  const { data, error, loading } = useAsync(() => api.models(), []);
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Modèles IA</h1>
          <p className="muted">Versions entraînées et déployées. Le déploiement et la validation se font par le pipeline ML (traçabilité).</p>
        </div>
      </div>
      <ErrorNotice message={error} />
      {loading ? <Loading /> : data?.length ? data.map((m) => (
        <Card key={`${m.pathology}-${m.version}`} title={<>{PATHOLOGY_LABELS[m.pathology]} — v{m.version}</>}
          actions={<div className="row">
            {m.active && <span className="badge badge-ok">Déployé</span>}
            {m.validated ? <span className="badge badge-ok">Validé cliniquement</span> : <span className="badge badge-warn">Non validé</span>}
          </div>}>
          <dl className="dl">
            <dt>Algorithme</dt><dd>{m.algorithm}</dd>
            <dt>Données d'entraînement</dt><dd>{m.data_source}</dd>
            <dt>Formulaire</dt><dd>v{m.form_version}</dd>
            <dt>Entraîné le</dt><dd>{formatDate(m.trained_at, true)}</dd>
            <dt>Seuils (moyen / élevé)</dt><dd>{m.thresholds.moyen} / {m.thresholds.eleve}</dd>
            <dt>Test — sensibilité / spécificité</dt><dd>{pct(m.test_sensitivity)} / {pct(m.test_specificity)}</dd>
            <dt>Test — ROC-AUC / PR-AUC</dt><dd>{m.test_roc_auc ?? "—"} / {m.test_pr_auc ?? "—"}</dd>
          </dl>
        </Card>
      )) : <div className="card empty">Aucun modèle entraîné.</div>}
    </>
  );
}

// --- Journal d'activité ---------------------------------------------------------------

const ACTIONS: Record<string, string> = {
  login: "Connexion", login_failed: "Échec de connexion", read: "Consultation", search: "Recherche", create: "Création",
  update: "Modification", decide: "Décision d'orientation", status_change: "Suivi", ai_run: "Analyse IA",
  ai_deferred: "Analyse IA différée", rights_change: "Changement de droits", password_change: "Mot de passe",
  password_change_failed: "Échec de changement de mot de passe", account_locked: "Compte bloqué",
  account_unlocked: "Compte débloqué", login_locked: "Connexion refusée (compte bloqué)",
  login_throttled: "Connexion refusée (trop de tentatives)",
};

export function Audit() {
  const [action, setAction] = useState("");
  const { data, error, loading } = useAsync(() => api.audit({ action: action || undefined, limit: 300 }), [action]);
  return (
    <>
      <div className="page-head"><h1>Journal d'activité</h1></div>
      <div className="card" style={{ maxWidth: 320 }}>
        <label className="field" style={{ margin: 0 }}><span className="field-label">Action</span>
          <select value={action} onChange={(e) => setAction(e.target.value)}>
            <option value="">Toutes</option>{Object.entries(ACTIONS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select></label>
      </div>
      <ErrorNotice message={error} />
      {loading ? <Loading /> : (
        <div className="card table-wrap" style={{ padding: 0 }}>
          <table>
            <thead><tr><th>Date</th><th>Utilisateur</th><th>Action</th><th>Objet</th><th>Détails</th></tr></thead>
            <tbody>
              {data?.map((e) => (
                <tr key={e.id}>
                  <td className="small">{formatDate(e.created_at, true)}</td>
                  <td>#{e.user_id ?? "—"}</td>
                  <td>{ACTIONS[e.action] ?? e.action}</td>
                  <td className="small">{e.entity}{e.entity_id ? ` ${e.entity_id.slice(0, 8)}` : ""}</td>
                  <td className="small muted">{Object.keys(e.details).length ? JSON.stringify(e.details) : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

// --- État du système -------------------------------------------------------------

const SOURCES: Record<string, string> = { api: "API", engine: "Moteur IA", web: "Site Web", mobile: "Application mobile" };

function duration(seconds: number) {
  const h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60);
  return h ? `${h} h ${m} min` : `${m} min`;
}

export function SystemPage() {
  const status = useAsync(() => api.systemStatus(), []);
  const [source, setSource] = useState("");
  const [search, setSearch] = useState("");
  const errors = useAsync(() => api.systemErrors({ source: source || undefined, request_id: search.trim() || undefined }), [source, search]);
  const [open, setOpen] = useState<number | null>(null);

  const resolve = async (id: number) => {
    await api.resolveError(id);
    errors.reload();
    status.reload();
  };

  const s = status.data;
  const badge = (ok: boolean, text: string) => <span className={`badge ${ok ? "badge-ok" : "badge-alert"}`}>{text}</span>;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>État du système</h1>
          <p className="muted">Disponibilité des composants et erreurs techniques. Aucune donnée de patiente n'est enregistrée ici.</p>
        </div>
        <button className="btn" onClick={() => { status.reload(); errors.reload(); }}>Actualiser</button>
      </div>
      <ErrorNotice message={status.error} />
      {s && (
        <>
          <div className="grid grid-4" style={{ marginBottom: 16 }}>
            <div className="card stat" style={{ marginBottom: 0 }}>
              <span className="stat-label">État global</span>
              <span className="stat-value" style={{ fontSize: "1.3rem" }}>{badge(s.status === "ok", s.status === "ok" ? "Opérationnel" : "Dégradé")}</span>
            </div>
            <div className="card stat" style={{ marginBottom: 0 }}>
              <span className="stat-label">Base de données</span>
              <span className="stat-value" style={{ fontSize: "1.3rem" }}>{badge(s.database.status === "ok", s.database.status === "ok" ? "Disponible" : "En erreur")}</span>
            </div>
            <div className="card stat" style={{ marginBottom: 0 }}>
              <span className="stat-label">Moteur IA</span>
              <span className="stat-value" style={{ fontSize: "1.3rem" }}>{badge(s.engine.status === "ok", s.engine.status === "ok" ? "Disponible" : "Injoignable")}</span>
              <span className="small muted">{s.engine.models ? Object.entries(s.engine.models).map(([p, v]) => `${p} v${v}`).join(", ") || "aucun modèle" : s.engine.detail}</span>
            </div>
            <div className="card stat" style={{ marginBottom: 0 }}>
              <span className="stat-label">Analyses IA en attente</span>
              <span className="stat-value">{s.screenings_pending_ai}</span>
            </div>
          </div>
          <div className="grid grid-2">
            <Card title="API (depuis le dernier démarrage)">
              <dl className="dl">
                <dt>En service depuis</dt><dd>{duration(s.api.uptime_seconds)}</dd>
                <dt>Requêtes</dt><dd>{s.api.requests}</dd>
                <dt>Erreurs serveur (5xx)</dt><dd>{s.api.server_errors}</dd>
                <dt>Refus / requêtes invalides (4xx)</dt><dd>{s.api.client_errors}</dd>
                <dt>Temps de réponse (médian / 95 %)</dt><dd>{s.api.latency_ms_p50 ?? "—"} ms / {s.api.latency_ms_p95 ?? "—"} ms</dd>
                <dt>Fichiers de logs</dt><dd className="small">{s.logs}</dd>
              </dl>
            </Card>
            <Card title="Erreurs des dernières 24 h">
              {Object.keys(s.errors_last_24h).length ? (
                <dl className="dl">{Object.entries(s.errors_last_24h).map(([k, v]) => <Fragment key={k}><dt>{SOURCES[k] ?? k}</dt><dd>{v}</dd></Fragment>)}</dl>
              ) : <p className="muted">Aucune erreur.</p>}
              <p className="small muted" style={{ marginTop: 8 }}>{s.unresolved_errors} erreur(s) non traitée(s) au total.</p>
            </Card>
          </div>
        </>
      )}

      <Card title="Erreurs à traiter">
        <div className="row" style={{ marginBottom: 12 }}>
          <select value={source} onChange={(e) => setSource(e.target.value)} style={{ maxWidth: 220 }} aria-label="Source">
            <option value="">Toutes les sources</option>
            {Object.entries(SOURCES).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <input type="search" placeholder="Référence communiquée par l'utilisateur" value={search} onChange={(e) => setSearch(e.target.value)} style={{ maxWidth: 340 }} />
        </div>
        <ErrorNotice message={errors.error} />
        {errors.loading ? <Loading /> : errors.data?.length ? (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Date</th><th>Source</th><th>Message</th><th>Référence</th><th /></tr></thead>
              <tbody>
                {errors.data.map((e) => (
                  <Fragment key={e.id}>
                    <tr className="clickable" onClick={() => setOpen(open === e.id ? null : e.id)}>
                      <td className="small">{formatDate(e.created_at, true)}</td>
                      <td>{SOURCES[e.source] ?? e.source}</td>
                      <td>{e.message}<div className="small muted">{e.path}{e.user_id ? ` · utilisateur #${e.user_id}` : ""}</div></td>
                      <td className="small"><code>{e.request_id ?? "—"}</code></td>
                      <td><button className="btn btn-sm" onClick={(ev) => { ev.stopPropagation(); resolve(e.id); }}>Marquer traitée</button></td>
                    </tr>
                    {open === e.id && (
                      <tr><td colSpan={5}>
                        <pre style={{ whiteSpace: "pre-wrap", fontSize: 12, margin: 0, maxHeight: 320, overflow: "auto" }}>
                          {Object.entries(e.details).map(([k, v]) => `${k} :\n${v}`).join("\n\n") || "Pas de détail."}
                        </pre>
                      </td></tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p className="muted">Aucune erreur à traiter.</p>}
      </Card>
    </>
  );
}
