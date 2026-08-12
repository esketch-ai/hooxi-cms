"""레거시 성공보수 정산 물리제거 (DBA P2.5 / 플랜 K.2 D2)

코드 경로 제거(증분 1~5) 완료 후 스키마를 물리 제거한다:
1. tb_settlement_snapshot.map_id 의 FK 제약 제거(테이블·컬럼은 감사 목적 보존).
2. tb_project_client_map 테이블 DROP(성공보수 정산 매핑 — 운수사 롤업으로 대체).
3. tb_project.unit_price·price_source 컬럼 DROP(§10.3 수기 단가).

- PostgreSQL 대상. SQLite는 ALTER/DROP 제약이 달라 no-op 스킵(0002 관례).
- 운영 데이터 0건(F.9-6)이라 데이터 손실 없음. downgrade는 구조만 재생성하며
  **데이터는 비가역**이다.

Revision ID: 0003_drop_legacy_settlement
Revises: 0002_fk_ondelete
Create Date: 2026-08-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_drop_legacy_settlement"
down_revision: Union[str, None] = "0002_fk_ondelete"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _fk_name(insp, table, col):
    for fk in insp.get_foreign_keys(table):
        if fk["constrained_columns"] == [col]:
            return fk["name"]
    return None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    insp = sa.inspect(bind)
    # 1) SettlementSnapshot.map_id FK 제거(테이블 보존)
    fk = _fk_name(insp, "tb_settlement_snapshot", "map_id")
    if fk:
        op.drop_constraint(fk, "tb_settlement_snapshot", type_="foreignkey")
    # 2) 성공보수 정산 매핑 테이블 DROP
    if "tb_project_client_map" in insp.get_table_names():
        op.drop_table("tb_project_client_map")
    # 3) 수기 단가 컬럼 DROP
    cols = {c["name"] for c in insp.get_columns("tb_project")}
    if "unit_price" in cols:
        op.drop_column("tb_project", "unit_price")
    if "price_source" in cols:
        op.drop_column("tb_project", "price_source")


def downgrade() -> None:
    """구조 재생성(데이터 비가역). PostgreSQL 대상, SQLite 스킵."""
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    # 3) 컬럼 복원
    op.add_column("tb_project", sa.Column("unit_price", sa.Numeric(15, 2)))
    op.add_column(
        "tb_project",
        sa.Column("price_source", sa.String(20), server_default="MANUAL"),
    )
    # 2) 매핑 테이블 복원(원 구조)
    op.create_table(
        "tb_project_client_map",
        sa.Column("map_id", sa.String(50), primary_key=True),
        sa.Column("project_id", sa.String(50), sa.ForeignKey("tb_project.project_id"), nullable=False),
        sa.Column("client_id", sa.String(50), sa.ForeignKey("tb_client.client_id"), nullable=False),
        sa.Column("asset_id", sa.String(50), sa.ForeignKey("tb_asset.asset_id")),
        sa.Column("allocation_ratio", sa.Numeric(5, 2)),
        sa.Column("success_fee_rate", sa.Numeric(5, 2)),
        sa.Column("expected_amount", sa.Numeric(15, 2)),
        sa.Column("settlement_status", sa.String(20), server_default="STANDBY"),
        sa.Column("billed_at", sa.DateTime()),
        sa.Column("billed_by", sa.String(50)),
        sa.Column("completed_at", sa.DateTime()),
        sa.Column("completed_by", sa.String(50)),
        sa.Column("paid_amount", sa.Numeric(15, 2)),
        sa.Column("payment_type", sa.String(20)),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
        sa.UniqueConstraint("project_id", "client_id", name="uq_project_client_map_slot"),
    )
    # 1) SettlementSnapshot.map_id FK 복원
    op.create_foreign_key(
        "fk_tb_settlement_snapshot_map_id",
        "tb_settlement_snapshot",
        "tb_project_client_map",
        ["map_id"],
        ["map_id"],
    )
