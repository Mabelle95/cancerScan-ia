import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { ROLE_LABELS, useAuth } from "../auth";

export function Layout() {
  const { user, can, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);

  return (
    <div className="shell">
      <div className="mobile-bar">
        <button className="btn btn-sm" onClick={() => setOpen(!open)} aria-expanded={open} aria-controls="sidebar">Menu</button>
        <strong style={{ color: "var(--primary)" }}>CancerScan</strong>
        <span />
      </div>
      <aside id="sidebar" className={`sidebar${open ? " open" : ""}`}>
        <div className="brand">
          <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
            <path fill="currentColor" d="M12 2c-1.6 0-3 1.3-3 3 0 1.4 1.3 3.6 2.1 5.3L6.4 20.6a1 1 0 0 0 1.8.8L12 13.6l3.8 7.8a1 1 0 0 0 1.8-.8l-4.7-10.3C13.7 8.6 15 6.4 15 5c0-1.7-1.4-3-3-3Zm0 2a1 1 0 0 1 1 1c0 .6-.5 1.8-1 2.9-.5-1.1-1-2.3-1-2.9a1 1 0 0 1 1-1Z" />
          </svg>
          CancerScan
        </div>
        <nav className="nav" onClick={close}>
          {can("patients:read") && <NavLink to="/patients">Patientes</NavLink>}
          {can("referrals:read") && <NavLink to="/orientations">Orientations et suivi</NavLink>}
          {can("stats:read") && <NavLink to="/statistiques">Statistiques</NavLink>}
          {(can("users:manage") || can("facilities:manage") || can("audit:read") || can("models:manage")) && (
            <>
              <div className="nav-section">Administration</div>
              {can("users:manage") && <NavLink to="/admin/utilisateurs">Utilisateurs</NavLink>}
              {can("facilities:manage") && <NavLink to="/admin/etablissements">Établissements</NavLink>}
              {can("models:manage") && <NavLink to="/admin/modeles">Modèles IA</NavLink>}
              {can("audit:read") && <NavLink to="/admin/journal">Journal d'activité</NavLink>}
              {can("audit:read") && <NavLink to="/admin/systeme">État du système</NavLink>}
            </>
          )}
        </nav>
        <div className="sidebar-footer">
          <div style={{ fontWeight: 600 }}>{user?.full_name}</div>
          <div className="muted">{user && ROLE_LABELS[user.role]}</div>
          <button className="btn btn-sm" style={{ marginTop: 8 }} onClick={logout}>Se déconnecter</button>
        </div>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
