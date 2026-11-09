import { Component, type ErrorInfo, type ReactNode } from "react";
import { reportError } from "../errorReporting";

/** Évite la page blanche : l'erreur est signalée au serveur et l'utilisateur peut recharger. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    reportError(Object.assign(error, { stack: `${error.stack ?? ""}\n${info.componentStack ?? ""}` }));
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="login-wrap">
        <div className="card" style={{ maxWidth: 480 }}>
          <h1>Une erreur est survenue</h1>
          <p className="muted">L'incident a été signalé automatiquement à l'équipe technique. Vos données enregistrées ne sont pas perdues.</p>
          <button className="btn btn-primary" onClick={() => window.location.assign("/")}>Revenir à l'accueil</button>
        </div>
      </div>
    );
  }
}
