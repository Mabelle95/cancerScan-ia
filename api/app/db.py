from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

_url = get_settings().database_url
# SQLite ne sert qu'aux tests et à la démonstration ; PostgreSQL en production.
_sqlite = _url.startswith("sqlite")
engine = create_engine(_url, pool_pre_ping=True, connect_args={"check_same_thread": False, "timeout": 30} if _sqlite else {})

if _sqlite:
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        # Une seule écriture à la fois : on attend son tour (30 s) au lieu d'échouer (« database is locked »),
        # et le mode WAL laisse les lectures se faire pendant une écriture.
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.close()
        dbapi_conn.isolation_level = None  # les transactions sont ouvertes ci-dessous

    @event.listens_for(engine, "begin")
    def _sqlite_begin_immediate(conn):
        # Sans cela, deux transactions qui lisent puis veulent écrire s'interbloquent : SQLite refuse
        # immédiatement la seconde (erreur 500 vue lors de synchronisations simultanées du mobile).
        # BEGIN IMMEDIATE réserve l'écriture dès le début : la seconde attend son tour.
        # Appliqué aussi aux lectures : presque toutes écrivent dans le journal d'audit (consultation d'un dossier).
        # Pour que l'attente reste courte, les traitements longs valident souvent (POST /sync : après chaque élément).
        # PostgreSQL, utilisé en production, n'a pas ce verrou global.
        conn.exec_driver_sql("BEGIN IMMEDIATE")
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
