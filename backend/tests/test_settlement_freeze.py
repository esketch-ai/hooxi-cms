"""정산 금액 동결 체계 (P0-A) — 청구 후 금액 불변, 스냅샷(R3-1)이 정본.

- 청구(BILLED) 후 단가·발행량 변경 시 해당 매핑 expected_amount 불변, STANDBY만 재계산
- COMPLETED 전이 시 재계산 금지 — 직전 BILLED 스냅샷 금액 승계(청구·입금 회차 일치)
- 확정(BILLED/COMPLETED) 매핑 upsert 409 (해제 409와 동일 규칙)
- 스냅샷 조회 API GET /settlements/{map_id}/snapshots — seq 오름차순
- 감사 로그: PROJECT_UNIT_PRICE(old→new)·PROJECT_MAP_UPSERT/RELEASE(배분율 요약)
"""

import models  # noqa: E402
from models import AuditLog, SettlementSnapshot  # noqa: E402

API = "/api/v1"
S = {}  # 테스트 간 공유 상태 (생성된 리소스 id)


def _db():
    return models.SessionLocal()


def _settlement_row(client, headers, map_id):
    resp = client.get(API + "/settlements", headers=headers)
    assert resp.status_code == 200, resp.text
    return next(i for i in resp.json()["items"] if i["map_id"] == map_id)


# ---------------------------------------------------------------------------
# 셋업 — 고객사 2곳 + 사업(1000 tCO₂ × 단가 10,000) + 매핑 2건
# ---------------------------------------------------------------------------
def test_freeze_setup(client, staff_headers):
    """셋업 — A(50%·10%)=500,000 / B(30%·10%)=300,000."""
    for name in ("동결운수", "동결에너지"):
        resp = client.post(
            API + "/clients",
            headers=staff_headers,
            json={"client_type": "TRANSPORT", "company_name": name},
        )
        assert resp.status_code == 201, resp.text
        S[name] = resp.json()["client_id"]

    resp = client.post(
        API + "/projects",
        headers=staff_headers,
        json={
            "project_name": "P0A 금액 동결 검증 사업",
            "project_status": "모니터링",
            "expected_credits": 1000,
            "unit_price": 10000,
            "manager_id": "u-manager",
        },
    )
    assert resp.status_code == 201, resp.text
    S["project_id"] = resp.json()["project_id"]

    for name, ratio, key in (("동결운수", 50, "map_a"), ("동결에너지", 30, "map_b")):
        resp = client.post(
            API + "/projects/" + S["project_id"] + "/clients",
            headers=staff_headers,
            json={"client_id": S[name], "allocation_ratio": ratio, "success_fee_rate": 10},
        )
        assert resp.status_code == 201, resp.text
        S[key] = resp.json()["map_id"]

    # 1000 × 50% × 10,000 × 10% = 500,000 / 1000 × 30% × 10,000 × 10% = 300,000
    assert _settlement_row(client, staff_headers, S["map_a"])["expected_amount"] == 500000
    assert _settlement_row(client, staff_headers, S["map_b"])["expected_amount"] == 300000


# ---------------------------------------------------------------------------
# 1. 청구 후 단가 변경 — BILLED 매핑 금액 동결, STANDBY만 재계산
# ---------------------------------------------------------------------------
def test_billed_amount_frozen_on_unit_price_change(client, staff_headers, admin_headers):
    """BILLED 후 단가 변경 → 해당 매핑 불변(500,000), STANDBY 매핑만 변동."""
    resp = client.put(
        API + "/settlements/" + S["map_a"] + "/status",
        headers=admin_headers,
        json={"settlement_status": "BILLED"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["expected_amount"] == 500000  # 청구 시점 서버 계산 확정

    resp = client.put(
        API + "/projects/" + S["project_id"] + "/unit-price",
        headers=staff_headers,
        json={"unit_price": 20000},
    )
    assert resp.status_code == 200, resp.text

    # BILLED(A)는 동결 — 스냅샷 정본. STANDBY(B)는 1000 × 30% × 20,000 × 10% = 600,000
    assert _settlement_row(client, staff_headers, S["map_a"])["expected_amount"] == 500000
    assert _settlement_row(client, staff_headers, S["map_b"])["expected_amount"] == 600000


def test_billed_amount_frozen_on_credits_change(client, staff_headers):
    """발행량 변경(사업 수정) 재계산 경로도 동일 — BILLED 동결·STANDBY 재계산."""
    resp = client.put(
        API + "/projects/" + S["project_id"],
        headers=staff_headers,
        json={"expected_credits": 2000},
    )
    assert resp.status_code == 200, resp.text
    rows = {m["map_id"]: m for m in resp.json()["clients"]}
    assert rows[S["map_a"]]["expected_amount"] == 500000  # 동결
    # 2000 × 30% × 20,000 × 10% = 1,200,000
    assert rows[S["map_b"]]["expected_amount"] == 1200000


# ---------------------------------------------------------------------------
# 2. 확정 매핑 변조 차단 — upsert 409
# ---------------------------------------------------------------------------
def test_billed_mapping_upsert_409(client, staff_headers):
    """BILLED 매핑 배분율 수정 시도 → 409 (해제 409와 동일 규칙)."""
    resp = client.post(
        API + "/projects/" + S["project_id"] + "/clients",
        headers=staff_headers,
        json={"client_id": S["동결운수"], "allocation_ratio": 90, "success_fee_rate": 50},
    )
    assert resp.status_code == 409
    assert "정산이 진행된 매핑은 수정할 수 없습니다" in resp.json()["detail"]
    # 값이 실제로 변조되지 않았는지 확인
    row = _settlement_row(client, staff_headers, S["map_a"])
    assert row["allocation_ratio"] == 50
    assert row["expected_amount"] == 500000


# ---------------------------------------------------------------------------
# 3. COMPLETED 전이 — 재계산 금지, BILLED 스냅샷 금액 승계
# ---------------------------------------------------------------------------
def test_completed_inherits_billed_snapshot_amount(client, admin_headers):
    """COMPLETED 스냅샷 금액 = BILLED 스냅샷 금액 (청구·입금 회차 일치)."""
    resp = client.put(
        API + "/settlements/" + S["map_a"] + "/status",
        headers=admin_headers,
        json={"settlement_status": "COMPLETED", "paid_amount": 500000, "payment_type": "FULL"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["settlement_status"] == "COMPLETED"
    assert body["expected_amount"] == 500000  # 단가 2배 변경에도 청구 금액 승계

    db = _db()
    try:
        snaps = (
            db.query(SettlementSnapshot)
            .filter(SettlementSnapshot.map_id == S["map_a"])
            .order_by(SettlementSnapshot.seq.asc())
            .all()
        )
        assert [s.action for s in snaps] == ["BILLED", "COMPLETED"]
        assert float(snaps[0].amount) == float(snaps[1].amount) == 500000
    finally:
        db.close()


def test_completed_mapping_upsert_409(client, staff_headers):
    """COMPLETED 매핑도 upsert 차단 — 409."""
    resp = client.post(
        API + "/projects/" + S["project_id"] + "/clients",
        headers=staff_headers,
        json={"client_id": S["동결운수"], "allocation_ratio": 50, "success_fee_rate": 10},
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# 4. 스냅샷 조회 API
# ---------------------------------------------------------------------------
def test_list_snapshots(client, staff_headers):
    """GET /settlements/{map_id}/snapshots — seq 오름차순, 동결 5요소 반환."""
    resp = client.get(
        API + "/settlements/" + S["map_a"] + "/snapshots", headers=staff_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    seqs = [s["seq"] for s in body["items"]]
    assert seqs == sorted(seqs)
    billed, completed = body["items"]
    assert billed["action"] == "BILLED"
    assert billed["amount"] == 500000
    assert billed["unit_price"] == 10000  # 청구 시점 단가 동결(현재 사업 단가는 20,000)
    assert billed["allocation_ratio"] == 50
    assert completed["action"] == "COMPLETED"
    assert completed["amount"] == 500000
    assert completed["paid_amount"] == 500000

    # 존재하지 않는 매핑 404 / 미인증 401
    assert client.get(API + "/settlements/no-such/snapshots", headers=staff_headers).status_code == 404
    assert client.get(API + "/settlements/" + S["map_a"] + "/snapshots").status_code == 401


# ---------------------------------------------------------------------------
# 5. 감사 로그 — 단가 변경·매핑 upsert/해제
# ---------------------------------------------------------------------------
def test_audit_unit_price_and_map_actions(client, staff_headers):
    """PROJECT_UNIT_PRICE(old→new)·PROJECT_MAP_UPSERT/RELEASE(배분율 요약) 적재."""
    # STANDBY 매핑(B) 배분율 수정 → UPSERT 로그, 이후 해제 → RELEASE 로그
    resp = client.post(
        API + "/projects/" + S["project_id"] + "/clients",
        headers=staff_headers,
        json={"client_id": S["동결에너지"], "allocation_ratio": 40, "success_fee_rate": 10},
    )
    assert resp.status_code == 201, resp.text
    resp = client.delete(
        API + "/projects/" + S["project_id"] + "/clients/" + S["map_b"],
        headers=staff_headers,
    )
    assert resp.status_code == 200, resp.text

    db = _db()
    try:
        price_logs = (
            db.query(AuditLog)
            .filter(
                AuditLog.action == "PROJECT_UNIT_PRICE",
                AuditLog.target_id == S["project_id"],
            )
            .all()
        )
        assert len(price_logs) == 1
        assert price_logs[0].old_value == "10000"  # 단가는 비밀값 아님 — old→new 기록
        assert price_logs[0].new_value == "20000"

        upsert_logs = (
            db.query(AuditLog)
            .filter(
                AuditLog.action == "PROJECT_MAP_UPSERT",
                AuditLog.target_id == S["map_b"],
            )
            .all()
        )
        # 최초 등록(30%) + 배분율 수정(30→40%)
        assert len(upsert_logs) == 2
        assert upsert_logs[0].old_value is None
        assert upsert_logs[0].new_value == "배분율 30%"
        assert upsert_logs[1].old_value == "배분율 30%"
        assert upsert_logs[1].new_value == "배분율 40%"

        release_logs = (
            db.query(AuditLog)
            .filter(
                AuditLog.action == "PROJECT_MAP_RELEASE",
                AuditLog.target_id == S["map_b"],
            )
            .all()
        )
        assert len(release_logs) == 1
        assert release_logs[0].old_value == "배분율 40%"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 6. 방어 — BILLED 스냅샷 없이 COMPLETED 전이(비정상 데이터) 시 현재 금액 유지
# ---------------------------------------------------------------------------
def test_completed_without_billed_snapshot_keeps_amount(client, staff_headers, admin_headers):
    """BILLED 스냅샷이 없으면(방어) 현재 expected_amount 유지 — 500 없이 동작."""
    resp = client.post(
        API + "/projects/" + S["project_id"] + "/clients",
        headers=staff_headers,
        json={"client_id": S["동결에너지"], "allocation_ratio": 20, "success_fee_rate": 10},
    )
    assert resp.status_code == 201, resp.text
    map_c = resp.json()["map_id"]
    # 2000 × 20% × 20,000 × 10% = 800,000
    assert resp.json()["expected_amount"] == 800000

    resp = client.put(
        API + "/settlements/" + map_c + "/status",
        headers=admin_headers,
        json={"settlement_status": "BILLED"},
    )
    assert resp.status_code == 200, resp.text

    # 비정상 상황 재현 — BILLED 스냅샷 강제 삭제 후 COMPLETED 전이
    db = _db()
    try:
        db.query(SettlementSnapshot).filter(SettlementSnapshot.map_id == map_c).delete()
        db.commit()
    finally:
        db.close()

    resp = client.put(
        API + "/settlements/" + map_c + "/status",
        headers=admin_headers,
        json={"settlement_status": "COMPLETED"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["expected_amount"] == 800000  # 현재 금액 유지(방어)


# ---------------------------------------------------------------------------
# 6. COMPLETED 스냅샷 issued_credits 승계 (QAQC 시나리오 P0-1) — 자족 시나리오
# ---------------------------------------------------------------------------
def test_completed_snapshot_inherits_billed_issued_credits(client, admin_headers, staff_headers):
    """COMPLETED 스냅샷 issued_credits = BILLED 스냅샷 값(승계).

    BILLED~COMPLETED 사이 project.issued_credits가 바뀌어도, 동결 금액(amount)과
    근거(issued_credits)가 일치해야 한다. 수정 전에는 project 재조회로 변경값이 기록됐다.
    """
    resp = client.post(
        API + "/clients", headers=staff_headers,
        json={"client_type": "TRANSPORT", "company_name": "발행크레딧승계운수"},
    )
    assert resp.status_code == 201, resp.text
    cid = resp.json()["client_id"]
    resp = client.post(
        API + "/projects", headers=staff_headers,
        json={"project_name": "발행크레딧 승계 검증", "project_status": "모니터링",
              "expected_credits": 1000, "unit_price": 10000, "manager_id": "u-manager"},
    )
    assert resp.status_code == 201, resp.text
    pid = resp.json()["project_id"]
    resp = client.post(
        API + "/projects/" + pid + "/clients", headers=staff_headers,
        json={"client_id": cid, "allocation_ratio": 50, "success_fee_rate": 10},
    )
    assert resp.status_code == 201, resp.text
    map_id = resp.json()["map_id"]

    # BILLED 전 발행 크레딧 = 100 (직접 세팅 — 발급완료 흐름 대체)
    db = _db()
    try:
        db.get(models.Project, pid).issued_credits = 100
        db.commit()
    finally:
        db.close()

    resp = client.put(
        API + "/settlements/" + map_id + "/status", headers=admin_headers,
        json={"settlement_status": "BILLED"},
    )
    assert resp.status_code == 200, resp.text

    # BILLED 후 발행 크레딧 변경 (100 → 999)
    db = _db()
    try:
        db.get(models.Project, pid).issued_credits = 999
        db.commit()
    finally:
        db.close()

    resp = client.put(
        API + "/settlements/" + map_id + "/status", headers=admin_headers,
        json={"settlement_status": "COMPLETED", "paid_amount": 500000, "payment_type": "FULL"},
    )
    assert resp.status_code == 200, resp.text

    db = _db()
    try:
        snaps = (
            db.query(SettlementSnapshot)
            .filter(SettlementSnapshot.map_id == map_id)
            .order_by(SettlementSnapshot.seq.asc())
            .all()
        )
        assert [s.action for s in snaps] == ["BILLED", "COMPLETED"]
        assert float(snaps[0].issued_credits) == 100
        # 승계값(100)이어야 함 — 변경된 999가 아니어야 한다
        assert float(snaps[1].issued_credits) == 100
    finally:
        db.close()
