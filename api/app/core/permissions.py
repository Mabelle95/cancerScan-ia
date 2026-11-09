from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    AGENT = "agent_sante"
    MEDECIN = "medecin"
    SPECIALISTE = "specialiste"
    RESPONSABLE = "responsable_sanitaire"


class Perm(StrEnum):
    PATIENTS_READ = "patients:read"
    PATIENTS_WRITE = "patients:write"
    SCREENINGS_READ = "screenings:read"
    SCREENINGS_WRITE = "screenings:write"
    EXAMS_WRITE = "exams:write"
    REFERRALS_READ = "referrals:read"
    REFERRALS_DECIDE = "referrals:decide"
    STATS_READ = "stats:read"
    USERS_MANAGE = "users:manage"
    FACILITIES_MANAGE = "facilities:manage"
    AUDIT_READ = "audit:read"
    MODELS_MANAGE = "models:manage"


# L'administrateur gère la plateforme mais n'accède pas aux dossiers médicaux (moindre privilège).
ROLE_PERMISSIONS: dict[Role, set[Perm]] = {
    Role.ADMIN: {Perm.USERS_MANAGE, Perm.FACILITIES_MANAGE, Perm.AUDIT_READ, Perm.MODELS_MANAGE, Perm.STATS_READ},
    Role.AGENT: {Perm.PATIENTS_READ, Perm.PATIENTS_WRITE, Perm.SCREENINGS_READ, Perm.SCREENINGS_WRITE, Perm.REFERRALS_READ},
    Role.MEDECIN: {
        Perm.PATIENTS_READ, Perm.PATIENTS_WRITE, Perm.SCREENINGS_READ, Perm.SCREENINGS_WRITE,
        Perm.EXAMS_WRITE, Perm.REFERRALS_READ, Perm.REFERRALS_DECIDE, Perm.STATS_READ,
    },
    Role.SPECIALISTE: {Perm.PATIENTS_READ, Perm.SCREENINGS_READ, Perm.EXAMS_WRITE, Perm.REFERRALS_READ, Perm.REFERRALS_DECIDE},
    Role.RESPONSABLE: {Perm.STATS_READ},
}


def has_permission(role: str, perm: Perm) -> bool:
    return perm in ROLE_PERMISSIONS.get(Role(role), set())
