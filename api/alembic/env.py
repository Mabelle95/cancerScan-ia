from logging.config import fileConfig

from alembic import context
from sqlalchemy import String

from app import models  # noqa: F401  (enregistre les tables)
from app.core.crypto import EncryptedString
from app.db import Base, engine

if context.config.config_file_name:
    fileConfig(context.config.config_file_name)


def render_item(type_, obj, autogen_context):
    # Les colonnes chiffrées sont stockées comme du texte : la migration ne dépend pas du code applicatif.
    if type_ == "type" and isinstance(obj, EncryptedString):
        return f"sa.String(length={obj.impl.length})"
    return False


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, render_item=render_item, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
