from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, Text, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .settings import get_settings


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ContainerRun(TimestampMixin, Base):
    __tablename__ = "container_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    audit_run_id: Mapped[str] = mapped_column(String(128), index=True)
    project_id: Mapped[str] = mapped_column(String(128), index=True)
    container_id: Mapped[str] = mapped_column(String(128), unique=True)
    image: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), default="created")
    labels: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class RuntimeNetwork(TimestampMixin, Base):
    __tablename__ = "runtime_networks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    audit_run_id: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    status: Mapped[str] = mapped_column(String(32), default="created")


class AgentTemplateRecord(TimestampMixin, Base):
    __tablename__ = "agent_templates"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    body: Mapped[dict[str, Any]] = mapped_column(JSON)


class McpTemplateRecord(TimestampMixin, Base):
    __tablename__ = "mcp_templates"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    body: Mapped[dict[str, Any]] = mapped_column(JSON)


settings = get_settings()
engine = create_async_engine(settings.postgres_async_dsn, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
