"""마감 리뷰 권고 검증 — 스냅샷 유니크 인덱스.

권고 2 — tb_settlement_snapshot (map_id, seq) 유니크 인덱스 존재·멱등·실효성.

주의: 레거시 정산 라우터(/settlements)·참여 고객사 매핑(tb_project_client_map)·수기 단가(§10.3)
  물리 제거로 단가 감사(PROJECT_UNIT_PRICE)·상태 전이 동시성(409) 테스트는 삭제.
  SettlementSnapshot 모델·유니크 인덱스는 보존되므로(증분 5) map_id는 임의 문자열로 직접
  적재해 인덱스 실효성만 검증한다.
"""

from sqlalchemy import inspect as sa_inspect

import models
from models import SettlementSnapshot

API = "/api/v1"
S = {}  # 테스트 간 공유 상태 (생성된 리소스 id)


def _db():
    return models.SessionLocal()


# ---------------------------------------------------------------------------
# 셋업 — 스냅샷 유니크 인덱스 검증용 map_id(임의 문자열)만 확보
#   (tb_project_client_map 물리 제거로 map_id는 순수 감사 문자열)
# ---------------------------------------------------------------------------
def test_reco_setup(client, staff_headers):
    S["map_id"] = "legacy-map-리뷰권고"


# ---------------------------------------------------------------------------
# 권고 2 — tb_settlement_snapshot (map_id, seq) 유니크 인덱스
#    (레거시 정산 라우터 제거로 상태 전이 동시성 테스트는 삭제. 모델/인덱스는 유지.)
# ---------------------------------------------------------------------------
def test_snapshot_unique_index_present_and_idempotent(client):
    target_cols = {"map_id", "seq"}

    def _has_unique():
        insp = sa_inspect(models.engine)
        return any(
            set(uc.get("column_names") or []) == target_cols
            for uc in insp.get_unique_constraints("tb_settlement_snapshot")
        ) or any(
            ix.get("unique") and set(ix.get("column_names") or []) == target_cols
            for ix in insp.get_indexes("tb_settlement_snapshot")
        )

    assert _has_unique()
    models.ensure_schema()  # 재실행해도 예외·중복 생성 없음 (멱등)
    assert _has_unique()


def test_snapshot_duplicate_seq_rejected(client):
    """유니크 실효성 — 같은 (map_id, seq) 직접 INSERT는 IntegrityError."""
    from sqlalchemy.exc import IntegrityError

    # 기준 스냅샷 1건 (레거시 정산 라우터 제거로 직접 적재)
    db = _db()
    try:
        db.add(
            SettlementSnapshot(
                map_id=S["map_id"], seq=1, action="BILLED", created_by="u-admin"
            )
        )
        db.commit()
    finally:
        db.close()

    db = _db()
    try:
        db.add(
            SettlementSnapshot(
                map_id=S["map_id"], seq=1, action="BILLED", created_by="u-admin"
            )
        )
        try:
            db.commit()
            raised = False
        except IntegrityError:
            db.rollback()
            raised = True
    finally:
        db.close()
    assert raised
