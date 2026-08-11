"""Alembic 환경 — hooxi-cms.

점진·저위험 도입(부록 M / DBA P1.2):
- 컬럼/인덱스 추가는 기존 `models.ensure_schema()`가 부팅 시 계속 담당.
- Alembic은 **파괴적/제약 변경**(FK ON DELETE, 레거시 컬럼·테이블 DROP)만 버전 관리한다.
- 대상 DB URL은 앱과 동일하게 환경변수 DATABASE_URL을 우선 사용.
"""
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# backend/ 를 import 경로에 추가 (models 로드용)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import Base  # noqa: E402

config = context.config

# 앱과 동일한 DATABASE_URL 우선(없으면 alembic.ini의 sqlalchemy.url)
_db_url = os.getenv("DATABASE_URL")
if _db_url:
    config.set_main_option("sqlalchemy.url", _db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=url.startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
