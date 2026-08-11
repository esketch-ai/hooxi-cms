"""마감 리뷰 권고 검증 — 일반 수정 경유 단가 감사 + 스냅샷 유니크 인덱스.

권고 1 — PUT /projects/{id} 경유 단가 변경도 전용 엔드포인트와 동일하게
  PROJECT_UNIT_PRICE 감사(old→new, {:g})·price_source=MANUAL 적재.
  단가 미포함/동일 값 수정은 감사 미적재.
권고 2 — tb_settlement_snapshot (map_id, seq) 유니크 인덱스 존재·멱등·실효성.

주의: 레거시 정산 라우터(/settlements) 제거로 상태 전이 동시성(409) 테스트는 삭제.
  SettlementSnapshot 모델·유니크 인덱스는 유지되므로 인덱스 실효성만 직접 검증한다.
"""

from sqlalchemy import inspect as sa_inspect

import models
from models import AuditLog, SettlementSnapshot

API = "/api/v1"
S = {}  # 테스트 간 공유 상태 (생성된 리소스 id)


def _db():
    return models.SessionLocal()


def _price_logs(project_id):
    db = _db()
    try:
        return (
            db.query(AuditLog)
            .filter(
                AuditLog.action == "PROJECT_UNIT_PRICE",
                AuditLog.target_id == project_id,
            )
            .order_by(AuditLog.created_at.asc())
            .all()
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 셋업 — 고객사 + 사업(1000 tCO₂ × 단가 10,000) + 매핑 1건
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
            "unit_price": 10000,
            "manager_id": "u-manager",
        },
    )
    assert resp.status_code == 201, resp.text
    S["project_id"] = resp.json()["project_id"]

    resp = client.post(
        API + "/projects/" + S["project_id"] + "/clients",
        headers=staff_headers,
        json={"client_id": S["client_id"], "allocation_ratio": 50, "success_fee_rate": 10},
    )
    assert resp.status_code == 201, resp.text
    S["map_id"] = resp.json()["map_id"]
    # 1000 × 50% × 10,000 × 10% = 500,000
    assert resp.json()["expected_amount"] == 500000


# ---------------------------------------------------------------------------
# 1. 권고 1 — 일반 PUT /projects/{id} 경유 단가 변경 감사
# ---------------------------------------------------------------------------
def test_general_update_unit_price_audited(client, staff_headers):
    """PUT /projects/{id}로 단가 변경 → PROJECT_UNIT_PRICE(old→new) 감사 + MANUAL."""
    resp = client.put(
        API + "/projects/" + S["project_id"],
        headers=staff_headers,
        json={"unit_price": 20000, "project_name": "리뷰 권고 검증 사업(수정)"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["price_source"] == "MANUAL"
    # 재계산 경로도 기존과 동일 — 1000 × 50% × 20,000 × 10% = 1,000,000
    assert resp.json()["clients"][0]["expected_amount"] == 1000000

    logs = _price_logs(S["project_id"])
    assert len(logs) == 1
    assert logs[0].old_value == "10000"  # {:g} 포맷 — 전용 엔드포인트와 동일
    assert logs[0].new_value == "20000"


def test_general_update_same_or_absent_price_not_audited(client, staff_headers):
    """단가 미포함·동일 값 수정은 감사 미적재 (변경 없음 = 기록 없음)."""
    # 단가 미포함
    resp = client.put(
        API + "/projects/" + S["project_id"],
        headers=staff_headers,
        json={"project_name": "리뷰 권고 검증 사업"},
    )
    assert resp.status_code == 200, resp.text
    # 동일 값
    resp = client.put(
        API + "/projects/" + S["project_id"],
        headers=staff_headers,
        json={"unit_price": 20000},
    )
    assert resp.status_code == 200, resp.text
    assert len(_price_logs(S["project_id"])) == 1  # 그대로 1건


def test_general_update_price_to_null_audited(client, staff_headers):
    """단가 → null(미정) 변경도 전용 엔드포인트와 동일하게 감사 (new=None)."""
    resp = client.put(
        API + "/projects/" + S["project_id"],
        headers=staff_headers,
        json={"unit_price": None},
    )
    assert resp.status_code == 200, resp.text
    logs = _price_logs(S["project_id"])
    assert len(logs) == 2
    assert logs[1].old_value == "20000"
    assert logs[1].new_value is None

    # 후속 테스트를 위해 단가 복원 (감사 3건째)
    resp = client.put(
        API + "/projects/" + S["project_id"],
        headers=staff_headers,
        json={"unit_price": 20000},
    )
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# 2. 권고 2 — tb_settlement_snapshot (map_id, seq) 유니크 인덱스
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
