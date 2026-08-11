"""FK ON DELETE 정책 승격 (DBA P1.3)

자식 FK에 ondelete를 넣어 앱 수기 cleanup(delete_project·_cascade_delete_client 등)의
DB 백스톱을 만든다. 기존 배포 DB의 FK를 DROP 후 ondelete 포함으로 재생성한다(점진·저위험).

- PostgreSQL 대상. SQLite는 ALTER로 FK 변경이 불가하므로 no-op으로 스킵한다.
- 자동 생성된 제약명은 환경별로 다를 수 있어 하드코딩하지 않고 inspector로 실제 FK 제약명을
  조회해 DROP한다(관례는 `<table>_<column>_fkey`이나 신뢰하지 않는다).

Revision ID: 0002_fk_ondelete
Revises: 0001_baseline
Create Date: 2026-08-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002_fk_ondelete"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, column, ref_table, ref_column, ondelete) — 정책표(DBA P1.3)
_SPECS = [
    ("tb_project_vehicle", "project_id", "tb_project", "project_id", "CASCADE"),
    ("tb_project_vehicle", "client_id", "tb_client", "client_id", "SET NULL"),
    ("tb_project_vehicle", "asset_id", "tb_asset", "asset_id", "SET NULL"),
    (
        "tb_project_vehicle",
        "client_vehicle_id",
        "tb_client_vehicle",
        "vehicle_id",
        "SET NULL",
    ),
    ("tb_project_sale", "project_id", "tb_project", "project_id", "CASCADE"),
    ("tb_purchase_invoice", "project_id", "tb_project", "project_id", "CASCADE"),
    ("tb_purchase_invoice", "client_id", "tb_client", "client_id", "SET NULL"),
    ("tb_project_stage", "project_id", "tb_project", "project_id", "CASCADE"),
    ("tb_client_vehicle", "client_id", "tb_client", "client_id", "SET NULL"),
    ("tb_client_vehicle", "asset_id", "tb_asset", "asset_id", "SET NULL"),
]


def _fk_name(insp, table, col):
    """단일 컬럼 FK의 실제 제약명을 조회(없으면 None)."""
    for fk in insp.get_foreign_keys(table):
        if fk["constrained_columns"] == [col]:
            return fk["name"]
    return None


def _rebuild(specs):
    """각 FK를 실제 제약명으로 DROP 후 spec대로 재생성한다."""
    bind = op.get_bind()
    # SQLite는 ALTER로 FK 변경 불가 → 스킵(no-op). 이 마이그레이션은 PostgreSQL 대상.
    if bind.dialect.name == "sqlite":
        return
    insp = sa.inspect(bind)
    for table, col, rt, rc, od in specs:
        name = _fk_name(insp, table, col)
        if name:
            op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(
            f"fk_{table}_{col}", table, rt, [col], [rc], ondelete=od
        )


def upgrade() -> None:
    _rebuild(_SPECS)


def downgrade() -> None:
    # 역동작: ondelete 없이 FK 재생성.
    _rebuild([(t, c, rt, rc, None) for (t, c, rt, rc, _od) in _SPECS])
