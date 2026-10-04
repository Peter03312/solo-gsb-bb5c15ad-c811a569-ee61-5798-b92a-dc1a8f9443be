"""数据库引擎、会话与初始化。"""
import time

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """建表（幂等）。数据库未就绪时按配置重试，便于 Compose 一键启动。"""
    last_exc: Exception | None = None
    for _ in range(settings.db_connect_retries):
        try:
            Base.metadata.create_all(bind=engine)
            return
        except OperationalError as exc:
            last_exc = exc
            time.sleep(settings.db_connect_retry_delay)
    raise RuntimeError("无法连接数据库，初始化失败") from last_exc
