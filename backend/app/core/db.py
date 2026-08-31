"""数据库引擎、会话与 Declarative Base。

SQLite 用于 MVP：零安装、单文件、便于演示与备份。
SQL 保持 Postgres 兼容（不使用 SQLite 方言特有语法），后期可平滑切换。
"""

from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import DateTime, Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import settings


def utcnow() -> datetime:
    """带时区的当前时间。全库统一用 UTC 存储。"""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


def _build_engine() -> Engine:
    kwargs: dict = {"echo": settings.debug, "future": True}
    if settings.is_sqlite:
        # FastAPI 的同步依赖会在线程池中执行，需允许跨线程使用连接
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(settings.database_url, **kwargs)


engine = _build_engine()

if settings.is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record) -> None:  # noqa: ANN001
        """SQLite 默认不校验外键，必须显式打开——否则 skill_code 的
        引用完整性形同虚设，而那是全系统的 join key。"""
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖注入用的会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """脚本/测试用的事务上下文。"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def create_all() -> None:
    """建表。MVP 阶段用 create_all 代替 Alembic（schema 仍在高频变动）。"""
    import app.models  # noqa: F401  确保所有模型完成注册

    settings.ensure_dirs()
    Base.metadata.create_all(bind=engine)


def drop_all() -> None:
    import app.models  # noqa: F401

    Base.metadata.drop_all(bind=engine)
