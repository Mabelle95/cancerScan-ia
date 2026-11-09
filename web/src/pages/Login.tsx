import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../auth";
import { Icon } from "../components/Icon";

/** Même écran que la connexion de l'application mobile : dégradé de marque, logo, carte blanche. */
export function Login() {
  const { user, login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
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
      const msg = (err as Error).message;
      setError(msg === "Identifiants invalides" ? "Identifiant ou mot de passe incorrect." : msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-wrap">
      <div className="login-inner">
        <div className="login-logo"><div><Icon name="medical" size={56} /></div></div>
        <h1 className="login-title">CancerScan</h1>
        <p className="login-sub">Dépistage du Cancer du Sein</p>
        <form className="login-card" onSubmit={submit}>
          <h2 style={{ fontSize: "1.4rem", marginBottom: 2 }}>Connexion</h2>
          <p className="muted" style={{ marginBottom: 20 }}>Accès réservé aux professionnels de santé</p>
          {error && <div className="notice notice-danger" role="alert">{error}</div>}
          <label className="field input-icon">
            <Icon name="person" />
            <input type="email" autoComplete="username" required placeholder="Identifiant (adresse e-mail)" aria-label="Identifiant"
              value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label className="field input-icon" style={{ position: "relative" }}>
            <Icon name="lock" />
            <input type={show ? "text" : "password"} autoComplete="current-password" required placeholder="Mot de passe" aria-label="Mot de passe"
              value={password} onChange={(e) => setPassword(e.target.value)} style={{ paddingRight: 92 }} />
            <button type="button" className="btn btn-sm" onClick={() => setShow(!show)}
              style={{ position: "absolute", right: 6, top: "50%", transform: "translateY(-50%)", border: 0 }}>
              {show ? "Masquer" : "Afficher"}
            </button>
          </label>
          <button className="btn btn-primary" style={{ width: "100%", minHeight: 52, fontSize: "1.05rem" }} disabled={busy}>
            {busy ? "Connexion…" : "Se connecter"}
          </button>
        </form>
        <p className="login-foot">Pas de compte ? Demandez-le à l'administrateur de votre district.</p>
        <p className="login-foot small"><span className="muted">Outil d'aide à la décision : il ne pose pas de diagnostic.</span></p>
      </div>
    </div>
  );
}
