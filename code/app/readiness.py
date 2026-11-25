"""Read-only database readiness checks for the web process."""

from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, select
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from app.storage import (
    ApiKey,
    ApiRequestLog,
    Dataset,
    DatasetRevision,
    DeveloperAccount,
    DeveloperSession,
    IngestionRun,
    SchemeFilterValue,
    SchemeIndex,
    SourceProbe,
    StoredRecord,
)

WEB_MODELS = (
    StoredRecord,
    Dataset,
    DatasetRevision,
    SchemeIndex,
    SchemeFilterValue,
    IngestionRun,
    SourceProbe,
    DeveloperAccount,
    DeveloperSession,
    ApiKey,
    ApiRequestLog,
)


def database_readiness(engine: Engine, expected_heads: frozenset[str]) -> str:
    try:
        with engine.connect() as connection:
            try:
                heads = MigrationContext.configure(connection).get_current_heads()
                if set(heads) != expected_heads:
                    return "schema_mismatch"
                # Zero-row reads check that the runtime account can access the columns it needs.
                for model in WEB_MODELS:
                    connection.execute(select(model).limit(0))
            except DBAPIError as exc:
                return "unavailable" if exc.connection_invalidated else "schema_unavailable"
    except SQLAlchemyError:
        return "unavailable"
    return "ok"
