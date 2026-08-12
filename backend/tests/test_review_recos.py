"""마감 리뷰 권고 검증 — 스냅샷 유니크 인덱스.

권고 2 — tb_settlement_snapshot (map_id, seq) 유니크 인덱스 존재·멱등·실효성.

주의: 레거시 정산 라우터(/settlements)·참여 고객사 매핑 CRUD·수기 단가(§10.3) 제거로
  단가 감사(PROJECT_UNIT_PRICE)·상태 전이 동시성(409) 테스트는 삭제.
  SettlementSnapshot·ProjectClientMap 모델·유니크 인덱스는 유지되므로(증분 5) 인덱스
  실효성만 직접 검증한다.
"""

from sqlalchemy import inspect as sa_inspect

import models
from models import ProjectClientMap, SettlementSnapshot

API = "/api/v1"
S = {}  # 테스트 간 공유 상태 (생성된 리소스 id)


def _db():
    return models.SessionLocal()


# ---------------------------------------------------------------------------
# 셋업 — 고객사 + 사업 + 매핑 1건(매핑 CRUD 은퇴로 DB 직접 삽입)
# ---------------------------------------------------------------------------
def test_reco_setup(client, staff_headers):
    resp = client.post(
        API + "/clients",
        headers=staff_headers,
        json={"client_type": "TRANSPORT", "company_name": "리뷰권고운수"},
    )
    assert resp.status_code == 201, resp.text
    S["client_id"] = resp.json()["client_id"]

    resp = client.post(
        API + "/projects",
        headers=staff_headers,
        json={
            "project_name": "리뷰 권고 검증 사업",
            "project_status": "모니터링",
            "expected_credits": 1000,
            "manager_id": "u-manager",
        },
    )
    assert resp.status_code == 201, resp.text
    S["project_id"] = resp.json()["project_id"]

    # 스냅샷 유니크 인덱스 실효성 검증에 필요한 map_id만 DB 직접 삽입으로 확보
    db = _db()
    try:
        m = ProjectClientMap(
            project_id=S["project_id"], client_id=S["client_id"],
            allocation_ratio=50, success_fee_rate=10, settlement_status="STANDBY",
        )
        db.add(m)
        db.commit()
        S["map_id"] = m.map_id
    finally:
        db.close()


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
