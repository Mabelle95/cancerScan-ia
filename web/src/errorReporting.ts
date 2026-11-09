// Remontée des erreurs du navigateur vers l'API (/client-errors), sans aucune donnée de patiente :
// uniquement le message, la pile d'appels et la page (chemin, sans paramètres de recherche).
import { tokenStore } from "./api";

const BASE = import.meta.env.VITE_API_URL ?? "/api/v1";
const recent = new Map<string, number>();

export function reportError(error: unknown, extra?: { requestId?: string }) {
  try {
    const err = error instanceof Error ? error : new Error(String(error));
    const key = `${err.name}:${err.message}`;
    const now = Date.now();
    if ((recent.get(key) ?? 0) > now - 30_000) return; // même erreur répétée : un seul rapport toutes les 30 s
    recent.set(key, now);
    const token = tokenStore.get();
    void fetch(`${BASE}/client-errors`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify({
        source: "web",
        message: `${err.name}: ${err.message}`.slice(0, 1000),
        stack: err.stack?.slice(0, 4000),
        screen: window.location.pathname.slice(0, 120),
        platform: navigator.userAgent.slice(0, 60),
        app_version: "0.1.0",
        request_id: extra?.requestId,
      }),
      keepalive: true,
    }).catch(() => { /* la remontée d'erreur ne doit jamais provoquer d'autre erreur */ });
  } catch { /* idem */ }
}

export function installGlobalErrorHandlers() {
  window.addEventListener("error", (e) => reportError(e.error ?? e.message));
  window.addEventListener("unhandledrejection", (e) => reportError(e.reason));
}
