"""마감 리뷰 권고 2건 검증 — 일반 수정 경유 단가 감사 + 정산 전이 동시성 방어.

권고 1 — PUT /projects/{id} 경유 단가 변경도 전용 엔드포인트와 동일하게
  PROJECT_UNIT_PRICE 감사(old→new, {:g})·price_source=MANUAL 적재.
  단가 미포함/동일 값 수정은 감사 미적재.
권고 2 — 정산 상태 전이 조건부 UPDATE (P0-B 준용):
  스냅샷 이후 다른 사용자가 먼저 전이한 경우 409 + 스냅샷·감사 미적재(phantom 방지),
  tb_settlement_snapshot (map_id, seq) 유니크 인덱스 존재·멱등·실효성.

스레드 없이 결정적으로 재현: get_or_404 스냅샷 직후 같은 커넥션 raw UPDATE로
'다른 사용자의 선행 커밋'을 주입 → 조건부 UPDATE rowcount 0 경로 강제 (P0-B 패턴).
"""

from sqlalchemy import inspect as sa_inspect, text as sa_text

import models
from models import AuditLog, SettlementSnapshot
from routers import common as rcommon

API = "/api/v1"
SETTLE_CONFLICT_DETAIL = "다른 사용자가 방금 정산 상태를 변경했습니다. 새로고침 후 다시 시도하세요"
S = {}  # 테스트 간 공유 상태 (생성된 리소스 id)


def _db():
    return models.SessionLocal()


def _inject_after_snapshot(monkeypatch, model, target_id, sql, params):
    """get_or_404 스냅샷 직후 raw UPDATE 1회 주입 — 동시 변경 인터리빙 재현 (P0-B와 동일)."""
    orig = rcommon.get_or_404
    fired = {"done": False}

    def stale_get(db, m, pk, label):
        obj = orig(db, m, pk, label)
        if m is model and pk == target_id and not fired["done"]:
            fired["done"] = True
            db.execute(sa_text(sql), params)
        return obj

    monkeypatch.setattr(rcommon, "get_or_404", stale_get)


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
# 2. 권고 2 — 정산 상태 전이 조건부 UPDATE (스냅샷 불일치 409)
# ---------------------------------------------------------------------------
def test_settlement_status_stale_conflict_409(client, admin_headers, monkeypatch):
    """스냅샷(STANDBY) 이후 다른 사용자가 BILLED로 바꾼 상황 → rowcount 0 → 409."""
    _inject_after_snapshot(
        monkeypatch,
        models.ProjectClientMap,
        S["map_id"],
        "UPDATE tb_project_client_map SET settlement_status='BILLED' WHERE map_id=:m",
        {"m": S["map_id"]},
    )
    resp = client.put(
        API + "/settlements/" + S["map_id"] + "/status",
        headers=admin_headers,
        json={"settlement_status": "BILLED"},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == SETTLE_CONFLICT_DETAIL


def test_settlement_conflict_no_phantom_snapshot_or_audit(client, staff_headers):
    """409 반려 건은 실제 전이가 아니므로 스냅샷·감사 로그가 없어야 한다."""
    resp = client.get(
        API + "/settlements/" + S["map_id"] + "/snapshots", headers=staff_headers
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    # 주입분 포함 롤백 — 상태도 STANDBY 그대로
    resp = client.get(API + "/settlements", headers=staff_headers)
    row = next(i for i in resp.json()["items"] if i["map_id"] == S["map_id"])
    assert row["settlement_status"] == "STANDBY"
    assert row["billed_at"] is None

    db = _db()
    try:
        logs = (
            db.query(AuditLog)
            .filter(
                AuditLog.action == "SETTLEMENT_CHANGE",
                AuditLog.target_id == S["map_id"],
            )
            .count()
        )
    finally:
        db.close()
    assert logs == 0


def test_settlement_transition_order_check_preserved(client, admin_headers):
    """기존 검증 순서·detail 보존 — 전이 사전 위반(STANDBY→COMPLETED)은 여전히 409."""
    resp = client.put(
        API + "/settlements/" + S["map_id"] + "/status",
        headers=admin_headers,
        json={"settlement_status": "COMPLETED"},
    )
    assert resp.status_code == 409
    assert "STANDBY→BILLED→COMPLETED 순서로만" in resp.json()["detail"]


def test_settlement_status_normal_path_still_works(client, staff_headers, admin_headers):
    """경합 없는 전이는 그대로 200 — 스냅샷·부수 필드(billed_at 등) 원자 반영."""
    resp = client.put(
        API + "/settlements/" + S["map_id"] + "/status",
        headers=admin_headers,
        json={"settlement_status": "BILLED"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["settlement_status"] == "BILLED"
    assert body["billed_at"] is not None
    # 청구 시점 서버 계산 확정 — 1000 × 50% × 20,000 × 10% = 1,000,000
    assert body["expected_amount"] == 1000000

    resp = client.put(
        API + "/settlements/" + S["map_id"] + "/status",
        headers=admin_headers,
        json={"settlement_status": "COMPLETED", "paid_amount": 1000000, "payment_type": "FULL"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["settlement_status"] == "COMPLETED"
    assert body["completed_at"] is not None
    assert body["paid_amount"] == 1000000
    assert body["payment_type"] == "FULL"
    assert body["expected_amount"] == 1000000  # BILLED 스냅샷 승계

    resp = client.get(
        API + "/settlements/" + S["map_id"] + "/snapshots", headers=staff_headers
    )
    assert resp.json()["total"] == 2
    assert [s["action"] for s in resp.json()["items"]] == ["BILLED", "COMPLETED"]


# ---------------------------------------------------------------------------
# 3. 권고 2 — tb_settlement_snapshot (map_id, seq) 유니크 인덱스
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
