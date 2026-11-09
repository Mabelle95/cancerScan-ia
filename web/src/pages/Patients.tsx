import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { ErrorNotice, Loading, formatDate, patientAge, useAsync } from "../components/ui";

export function Patients() {
  const { can } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const [input, setInput] = useState(q);
  const { data, error, loading } = useAsync(() => api.searchPatients(q || undefined), [q]);

  // Recherche différée pendant la saisie
  useEffect(() => {
    const t = setTimeout(() => setParams(input ? { q: input } : {}, { replace: true }), 350);
    return () => clearTimeout(t);
  }, [input, setParams]);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Patientes</h1>
          <p className="muted">Rechercher un dossier avant d'en créer un nouveau, pour éviter les doublons.</p>
        </div>
        {can("patients:write") && <Link className="btn btn-primary" to="/patients/nouvelle">Nouvelle patiente</Link>}
      </div>
      <div className="card">
        <input type="search" placeholder="Code (CS-…), téléphone ou nom" value={input} onChange={(e) => setInput(e.target.value)}
          aria-label="Rechercher une patiente" autoFocus />
      </div>
      <ErrorNotice message={error} />
      {loading ? <Loading /> : (
        <div className="card table-wrap" style={{ padding: 0 }}>
          {data?.length ? (
            <table>
              <thead><tr><th>Code</th><th>Nom</th><th>Âge</th><th>Localité</th><th>Enregistrée le</th></tr></thead>
              <tbody>
                {data.map((p) => (
                  <tr key={p.id} className="clickable" onClick={() => navigate(`/patients/${p.id}`)}>
                    <td><Link to={`/patients/${p.id}`} onClick={(e) => e.stopPropagation()}>{p.code}</Link></td>
                    <td>{p.full_name ?? "—"}</td>
                    <td>{patientAge(p)}</td>
                    <td>{[p.locality, p.region].filter(Boolean).join(", ")}</td>
                    <td>{formatDate(p.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <div className="empty">{q ? "Aucune patiente trouvée." : "Aucune patiente enregistrée dans votre établissement."}</div>}
        </div>
      )}
    </>
  );
}
