import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../auth";

export function Login() {
  const { user, login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/" replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-wrap">
      <form className="card login-card" onSubmit={submit}>
        <h1 style={{ color: "var(--primary)" }}>CancerScan</h1>
        <p className="muted">Aide au dépistage et à l'orientation précoce des cancers du sein et gynécologiques.</p>
        {error && <div className="notice notice-danger" role="alert">{error}</div>}
        <label className="field">
          <span className="field-label">Adresse e-mail</span>
          <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="field">
          <span className="field-label">Mot de passe</span>
          <input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        <button className="btn btn-primary" style={{ width: "100%" }} disabled={busy}>{busy ? "Connexion…" : "Se connecter"}</button>
        <p className="field-help" style={{ marginTop: 16 }}>
          Outil d'aide à la décision : il ne pose pas de diagnostic. Le diagnostic relève des professionnels de santé.
        </p>
      </form>
    </div>
  );
}
