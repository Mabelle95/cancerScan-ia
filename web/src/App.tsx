import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import { Layout } from "./components/Layout";
import { Loading } from "./components/ui";
import { Audit, Facilities, Models, SystemPage, Users } from "./pages/admin/Admin";
import { Login } from "./pages/Login";
import { PatientDetail } from "./pages/PatientDetail";
import { PatientNew } from "./pages/PatientNew";
import { Patients } from "./pages/Patients";
import { Referrals } from "./pages/Referrals";
import { ScreeningForm } from "./pages/ScreeningForm";
import { ScreeningResult } from "./pages/ScreeningResult";
import { Stats } from "./pages/Stats";

function Protected({ perm, children }: { perm?: string; children: ReactNode }) {
  const { user, loading, can } = useAuth();
  if (loading) return <Loading />;
  if (!user) return <Navigate to="/connexion" replace />;
  if (perm && !can(perm)) return <div className="card empty">Vous n'avez pas accès à cette page.</div>;
  return <>{children}</>;
}

/** Page d'accueil selon le rôle. */
function Home() {
  const { can } = useAuth();
  if (can("patients:read")) return <Navigate to="/patients" replace />;
  if (can("stats:read")) return <Navigate to="/statistiques" replace />;
  if (can("users:manage")) return <Navigate to="/admin/utilisateurs" replace />;
  return <div className="card empty">Aucune fonctionnalité n'est associée à votre rôle.</div>;
}

export function App() {
  return (
    <Routes>
      <Route path="/connexion" element={<Login />} />
      <Route element={<Protected><Layout /></Protected>}>
        <Route index element={<Home />} />
        <Route path="patients" element={<Protected perm="patients:read"><Patients /></Protected>} />
        <Route path="patients/nouvelle" element={<Protected perm="patients:write"><PatientNew /></Protected>} />
        <Route path="patients/:id" element={<Protected perm="patients:read"><PatientDetail /></Protected>} />
        <Route path="patients/:id/depistage" element={<Protected perm="screenings:write"><ScreeningForm /></Protected>} />
        <Route path="depistages/:sid" element={<Protected perm="screenings:read"><ScreeningResult /></Protected>} />
        <Route path="depistages/:sid/modifier" element={<Protected perm="screenings:write"><ScreeningForm /></Protected>} />
        <Route path="orientations" element={<Protected perm="referrals:read"><Referrals /></Protected>} />
        <Route path="statistiques" element={<Protected perm="stats:read"><Stats /></Protected>} />
        <Route path="admin/utilisateurs" element={<Protected perm="users:manage"><Users /></Protected>} />
        <Route path="admin/etablissements" element={<Protected perm="facilities:manage"><Facilities /></Protected>} />
        <Route path="admin/modeles" element={<Protected perm="models:manage"><Models /></Protected>} />
        <Route path="admin/journal" element={<Protected perm="audit:read"><Audit /></Protected>} />
        <Route path="admin/systeme" element={<Protected perm="audit:read"><SystemPage /></Protected>} />
        <Route path="*" element={<div className="card empty">Page introuvable.</div>} />
      </Route>
    </Routes>
  );
}
