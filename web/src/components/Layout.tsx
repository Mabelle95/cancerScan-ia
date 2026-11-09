import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { ROLE_LABELS, useAuth } from "../auth";
import { Icon } from "./Icon";

export function Layout() {
  const { user, can, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);
  const initial = (user?.full_name ?? "?").trim().charAt(0).toUpperCase();
  const link = (to: string, icon: string, label: string) => (
    <NavLink to={to}><Icon name={icon} size={20} />{label}</NavLink>
  );

  return (
    <div className="shell">
      <div className="mobile-bar">
        <button className="btn btn-sm" onClick={() => setOpen(!open)} aria-expanded={open} aria-controls="sidebar">Menu</button>
        <strong className="row"><Icon name="medical" size={20} /> CancerScan</strong>
        <span />
      </div>
      <aside id="sidebar" className={`sidebar${open ? " open" : ""}`}>
        <div className="brand">
          <span className="brand-logo"><Icon name="medical" size={22} /></span>
          CancerScan
        </div>
        <nav className="nav" onClick={close}>
          {can("patients:read") && link("/patients", "people", "Patientes")}
          {can("referrals:read") && link("/orientations", "route", "Orientations et suivi")}
          {can("stats:read") && link("/statistiques", "insights", "Statistiques")}
          {(can("users:manage") || can("facilities:manage") || can("audit:read") || can("models:manage")) && (
            <>
              <div className="nav-section">Administration</div>
              {can("users:manage") && link("/admin/utilisateurs", "users", "Utilisateurs")}
              {can("facilities:manage") && link("/admin/etablissements", "building", "Établissements")}
              {can("models:manage") && link("/admin/modeles", "brain", "Modèles IA")}
              {can("audit:read") && link("/admin/journal", "list", "Journal d'activité")}
              {can("audit:read") && link("/admin/systeme", "monitor", "État du système")}
            </>
          )}
        </nav>
        <div className="sidebar-footer">
          <span className="avatar">{initial}</span>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div style={{ fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{user?.full_name}</div>
            <div style={{ opacity: 0.8, fontSize: "0.8rem" }}>{user && ROLE_LABELS[user.role]}</div>
          </div>
          <button className="btn btn-sm" onClick={logout} title="Se déconnecter" aria-label="Se déconnecter"><Icon name="logout" size={18} /></button>
        </div>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
