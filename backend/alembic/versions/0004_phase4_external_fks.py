"""Phase 4 신규 컬럼 FK 승격 (ProjectSale.buyer_id·User.client_id/buyer_id)

INC-1/2에서 ensure_schema가 컬럼(VARCHAR)만 추가했으므로, 기존 배포 DB에
ondelete SET NULL FK 제약을 붙인다. 신규 DB는 create_all이 FK 포함 생성하므로 무관.

- PostgreSQL 대상. SQLite는 ALTER FK 불가 → no-op 스킵.
- 참조 테이블(tb_buyer)은 배포 시 create_all이 먼저 생성한다(마이그레이션은 배포 후 수동 적용).

Revision ID: 0004_phase4_external_fks
Revises: 0003_drop_legacy_settlement
Create Date: 2026-08-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_phase4_external_fks"
down_revision: Union[str, None] = "0003_drop_legacy_settlement"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, col, ref_table, ref_col) — 전부 ondelete SET NULL
_SPECS = [
    ("tb_project_sale", "buyer_id", "tb_buyer", "buyer_id"),
    ("tb_user", "client_id", "tb_client", "client_id"),
    ("tb_user", "buyer_id", "tb_buyer", "buyer_id"),
]


def _has_fk(insp, table, col):
    return any(fk["constrained_columns"] == [col] for fk in insp.get_foreign_keys(table))


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    insp = sa.inspect(bind)
    for table, col, rt, rc in _SPECS:
        if not _has_fk(insp, table, col):  # 멱등 — 이미 있으면 스킵
            op.create_foreign_key(f"fk_{table}_{col}", table, rt, [col], [rc], ondelete="SET NULL")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    insp = sa.inspect(bind)
    for table, col, _rt, _rc in _SPECS:
        for fk in insp.get_foreign_keys(table):
            if fk["constrained_columns"] == [col] and fk.get("name"):
                op.drop_constraint(fk["name"], table, type_="foreignkey")
