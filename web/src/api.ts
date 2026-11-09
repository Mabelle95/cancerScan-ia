// Client de l'API CancerScan. Les types reprennent les schémas Pydantic de api/app/schemas.py.

const BASE = import.meta.env.VITE_API_URL ?? "/api/v1";
const TOKEN_KEY = "cancerscan.token";

export type Role = "admin" | "agent_sante" | "medecin" | "specialiste" | "responsable_sanitaire";
export type Pathology = "sein" | "col" | "ovaire" | "endometre";
export type RiskLevel = "faible" | "moyen" | "eleve";
export type ScreeningStatus = "brouillon" | "soumis" | "analyse" | "valide";
export type ReferralStatus = "proposee" | "programmee" | "realisee" | "perdue_de_vue" | "annulee";
export type FieldValue = boolean | number | string | string[] | null;
export type FormData = Record<string, FieldValue>;

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  facility_id: number | null;
  is_active: boolean;
  mfa_enabled: boolean;
  created_at: string;
  last_login_at: string | null;
  locked_until?: string | null;
  failed_login_count?: number;
}

export interface Facility {
  id: number;
  code: string;
  name: string;
  region: string;
  district: string | null;
  level: string | null;
  is_active: boolean;
}

export interface FormOption { value: string; label: string; alert?: boolean }
export interface FormField {
  id: string;
  label: string;
  type: "boolean" | "integer" | "number" | "choice" | "multichoice" | "text" | "date";
  required?: boolean;
  min?: number;
  max?: number;
  unit?: string;
  options?: FormOption[];
  alert_when?: boolean;
  show_if?: { field: string; equals?: FieldValue; greater_than?: number };
  ml?: boolean;
  help?: string;
}
export interface FormSection { id: string; title: string; icon?: string; fields: FormField[] }
export interface FormDef { pathology: Pathology; title: string; version: string; validated: boolean; sections: FormSection[] }

export interface PatientSummary {
  id: string;
  code: string;
  full_name: string | null;
  birth_date: string | null;
  birth_year_estimated: number | null;
  region: string;
  locality: string | null;
  facility_id: number;
  created_at: string;
}
export interface Patient extends PatientSummary {
  phone: string | null;
  education_level: string | null;
  consent_given: boolean;
  consent_date: string | null;
  consent_research: boolean;
}

export interface Explanation { feature: string; label?: string; value?: FieldValue; contribution: number; direction?: "augmente" | "diminue" }
export interface Assessment {
  id: number;
  model_id: string;
  model_version: string;
  model_validated: boolean;
  score: number;
  risk_level: RiskLevel;
  explanations: Explanation[];
  created_at: string;
}
export interface Referral {
  id: number;
  screening_id: string;
  patient_id: string;
  proposed_level: RiskLevel | null;
  proposed_recommendation: string;
  final_decision: string | null;
  decided_by_id: number | null;
  decided_at: string | null;
  to_facility_id: number | null;
  reason: string | null;
  appointment_date: string | null;
  status: ReferralStatus;
  created_at: string;
  completed_at: string | null;
}
export interface ReferralListItem extends Referral { patient_code: string; pathology: Pathology }

export interface Screening {
  id: string;
  patient_id: string;
  pathology: Pathology;
  form_version: string;
  status: ScreeningStatus;
  data: FormData;
  alerts: { field: string; label: string }[];
  facility_id: number;
  created_at: string;
  submitted_at: string | null;
  assessments: Assessment[];
  referral: Referral | null;
}
export interface SubmitResult { screening: Screening; missing_required: string[]; errors: Record<string, string>; ai_pending: boolean }

export interface Exam {
  id: number;
  patient_id: string;
  screening_id: string | null;
  exam_type: string;
  result: string;
  conclusion: string | null;
  exam_date: string | null;
  source: string | null;
  created_at: string;
}

export interface AuditEntry {
  id: number;
  user_id: number | null;
  action: string;
  entity: string;
  entity_id: string | null;
  details: Record<string, unknown>;
  ip_address: string | null;
  created_at: string;
}

export type Counts = Record<string, number | null>;
export interface StatsOverview {
  scope: "etablissement" | "national";
  min_cell_size: number;
  totals: {
    patientes: number;
    depistages: number;
    avec_signes_alerte: number;
    references: number;
    references_realisees: number;
    taux_realisation: number | null;
    delai_median_jours: number | null;
    cas_confirmes: Counts;
  };
  par_pathologie: Counts;
  par_region: Counts;
  par_tranche_age: Counts;
  par_niveau_risque: Counts;
  statut_references: Counts;
  evolution_mensuelle: Counts;
}

export interface ModelInfo {
  pathology: Pathology;
  version: string;
  model_id: string;
  algorithm: string;
  active: boolean;
  validated: boolean;
  data_source: string;
  form_version: string;
  trained_at: string;
  thresholds: { moyen: number; eleve: number };
  test_roc_auc: number | null;
  test_pr_auc: number | null;
  test_sensitivity: number | null;
  test_specificity: number | null;
}

export class ApiError extends Error {
  constructor(public status: number, message: string, public detail?: unknown, public requestId?: string) {
    super(message);
  }
}

export const tokenStore = {
  get: (): string | null => {
    try { return sessionStorage.getItem(TOKEN_KEY); } catch { return null; }
  },
  set: (token: string | null) => {
    try {
      if (token) sessionStorage.setItem(TOKEN_KEY, token);
      else sessionStorage.removeItem(TOKEN_KEY);
    } catch { /* stockage indisponible : la session ne survivra pas au rechargement */ }
  },
};

let onUnauthorized: () => void = () => {};
export function setUnauthorizedHandler(handler: () => void) { onUnauthorized = handler; }

function errorMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown })?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // Erreurs de validation FastAPI : [{loc, msg}, …]
    return detail.map((d: { msg?: string }) => d.msg?.replace(/^Value error, /, "") ?? "Donnée invalide").join(" · ");
  }
  return status >= 500 ? "Erreur du serveur, réessayez plus tard." : `Erreur ${status}`;
}

export interface SystemStatus {
  status: "ok" | "degrade";
  version: string;
  api: { uptime_seconds: number; requests: number; server_errors: number; client_errors: number; latency_ms_p50: number | null; latency_ms_p95: number | null };
  database: { status: string; detail?: string };
  engine: { status: string; models?: Record<string, string>; allow_unvalidated?: boolean; detail?: string };
  errors_last_24h: Record<string, number>;
  unresolved_errors: number;
  screenings_pending_ai: number;
  logs: string;
}

export interface SystemError {
  id: number;
  source: string;
  level: string;
  message: string;
  request_id: string | null;
  path: string | null;
  user_id: number | null;
  details: Record<string, string>;
  resolved: boolean;
  created_at: string;
}

async function request<T>(method: string, path: string, body?: unknown, query?: Record<string, unknown>): Promise<T> {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v !== undefined && v !== null && v !== "" && v !== false) params.set(k, String(v));
  }
  const url = `${BASE}${path}${params.size ? `?${params}` : ""}`;
  const headers: Record<string, string> = {};
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let res: Response;
  try {
    res = await fetch(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError(0, "Serveur injoignable. Vérifiez votre connexion.");
  }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401 && path !== "/auth/login") onUnauthorized();
    const requestId = (data as { request_id?: string } | null)?.request_id ?? res.headers.get("X-Request-ID") ?? undefined;
    // Erreur serveur : le message contient déjà la référence à communiquer au support
    throw new ApiError(res.status, errorMessage(data, res.status), data, requestId);
  }
  return data as T;
}

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string; expires_in: number; user: User }>("POST", "/auth/login", { email, password }),
  me: () => request<{ user: User; permissions: string[] }>("GET", "/auth/me"),
  changePassword: (current_password: string, new_password: string) =>
    request<void>("POST", "/auth/change-password", { current_password, new_password }),

  forms: () => request<FormDef[]>("GET", "/forms"),

  searchPatients: (q?: string) => request<PatientSummary[]>("GET", "/patients", undefined, { q }),
  createPatient: (body: Record<string, unknown>) =>
    request<{ patient: Patient; possible_duplicates: PatientSummary[] }>("POST", "/patients", body),
  patient: (id: string) => request<Patient>("GET", `/patients/${id}`),
  patientScreenings: (id: string) => request<Screening[]>("GET", `/patients/${id}/screenings`),
  patientExams: (id: string) => request<Exam[]>("GET", `/patients/${id}/exams`),
  addExam: (id: string, body: Record<string, unknown>) => request<Exam>("POST", `/patients/${id}/exams`, body),
  createScreening: (patientId: string, pathology: Pathology, data: FormData, submit: boolean) =>
    request<SubmitResult>("POST", `/patients/${patientId}/screenings`, { pathology, data, submit }),

  screening: (id: string) => request<Screening>("GET", `/screenings/${id}`),
  updateScreening: (id: string, data: FormData) => request<SubmitResult>("PUT", `/screenings/${id}`, { data }),
  submitScreening: (id: string) => request<SubmitResult>("POST", `/screenings/${id}/submit`),
  processPending: () => request<{ pending: number; analysed: number }>("POST", "/screenings/process-pending"),

  referrals: (query: { status?: ReferralStatus; direction?: string; pending_decision?: boolean; overdue?: boolean }) =>
    request<ReferralListItem[]>("GET", "/referrals", undefined, query),
  decideReferral: (id: number, body: { final_decision: string; to_facility_id?: number | null; reason?: string; appointment_date?: string | null }) =>
    request<Referral>("POST", `/referrals/${id}/decision`, body),
  referralStatus: (id: number, status: ReferralStatus, appointment_date?: string) =>
    request<Referral>("PATCH", `/referrals/${id}/status`, { status, appointment_date }),

  facilities: (activeOnly = true) => request<Facility[]>("GET", "/facilities", undefined, { active_only: activeOnly ? "true" : "false" }),
  createFacility: (body: Omit<Facility, "id">) => request<Facility>("POST", "/facilities", body),
  updateFacility: (id: number, body: Omit<Facility, "id">) => request<Facility>("PUT", `/facilities/${id}`, body),

  users: () => request<User[]>("GET", "/users"),
  createUser: (body: Record<string, unknown>) => request<User>("POST", "/users", body),
  updateUser: (id: number, body: Record<string, unknown>) => request<User>("PATCH", `/users/${id}`, body),
  unlockUser: (id: number) => request<User>("POST", `/users/${id}/unlock`),

  audit: (query: { action?: string; entity?: string; limit?: number }) => request<AuditEntry[]>("GET", "/audit", undefined, query),
  models: () => request<ModelInfo[]>("GET", "/models"),
  systemStatus: () => request<SystemStatus>("GET", "/system/status"),
  systemErrors: (query: { source?: string; include_resolved?: boolean; request_id?: string }) =>
    request<SystemError[]>("GET", "/system/errors", undefined, query),
  resolveError: (id: number) => request<SystemError>("POST", `/system/errors/${id}/resolve`),
  stats: (query: { region?: string; pathology?: string; date_from?: string; date_to?: string }) =>
    request<StatsOverview>("GET", "/stats/overview", undefined, query),
};
