from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core import errors as error_handlers
from app.core.config import get_settings
from app.core.observability import RequestContextMiddleware, setup_logging
from app.routers import admin, auth, patients, referrals, screenings, stats, sync, system

settings = get_settings()
setup_logging(settings.log_dir, settings.log_level, service="api")

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "API de CancerScan — système d'aide au dépistage et à l'orientation précoce des cancers du sein et "
        "gynécologiques. **Outil d'aide à la décision : il ne pose pas de diagnostic.**"
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
# Ajouté en dernier = exécuté en premier : l'identifiant de requête existe pour toute la chaîne
app.add_middleware(RequestContextMiddleware)
error_handlers.install(app)

API_PREFIX = "/api/v1"
for module in (auth, admin, patients, screenings, referrals, stats, sync, system):
    app.include_router(module.router, prefix=API_PREFIX)


@app.get("/health", tags=["Supervision"])
def health():
    return {"status": "ok"}
