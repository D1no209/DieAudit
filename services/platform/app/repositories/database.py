from collections.abc import AsyncIterator

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text, inspect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateColumn

from app.domain.models import Base
from app.settings import get_settings


settings = get_settings()
engine = create_async_engine(settings.postgres_async_dsn, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(reconcile_schema)


def reconcile_schema(conn) -> None:
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue

        existing_columns = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing_columns:
                continue
            _add_missing_column(conn, table, column)

        existing_indexes = {index["name"] for index in inspector.get_indexes(table.name)}
        for index in table.indexes:
            if index.name not in existing_indexes:
                index.create(conn)


def _add_missing_column(conn, table, column) -> None:
    table_name = conn.dialect.identifier_preparer.quote(table.name)
    column_ddl = CreateColumn(column).compile(dialect=conn.dialect)
    if column.nullable or column.server_default is not None:
        conn.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column_ddl}")
        return

    column_name = conn.dialect.identifier_preparer.quote(column.name)
    column_type = column.type.compile(dialect=conn.dialect)
    default_sql = _default_sql_for_column(column)
    conn.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
    conn.exec_driver_sql(f"UPDATE {table_name} SET {column_name} = {default_sql} WHERE {column_name} IS NULL")
    conn.exec_driver_sql(f"ALTER TABLE {table_name} ALTER COLUMN {column_name} SET NOT NULL")


def _default_sql_for_column(column) -> str:
    default = column.default
    if default is not None and getattr(default, "is_scalar", False):
        return _literal_sql(default.arg, column)
    if default is not None and default.arg is dict:
        return "'{}'::json"
    if default is not None and default.arg is list:
        return "'[]'::json"

    if isinstance(column.type, Boolean):
        return "FALSE"
    if isinstance(column.type, Integer):
        return "0"
    if isinstance(column.type, JSON):
        return "'{}'::json"
    if isinstance(column.type, DateTime):
        return "NOW()"
    if isinstance(column.type, (String, Text)):
        return "''"
    return "''"


def _literal_sql(value, column) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (dict, list)) or isinstance(column.type, JSON):
        import json

        return "'" + json.dumps(value).replace("'", "''") + "'::json"
    return "'" + str(value).replace("'", "''") + "'"


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
