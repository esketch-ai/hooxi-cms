"""P2 스모크 테스트 — 자산(SCR-04)·감축 사업(SCR-06)·정산(SCR-07).

- 자산 CRUD + AES-256-GCM 암호화 저장(평문 미노출) + reveal-auth(감사 로그·키 미설정 503)
- 프로젝트 CRUD + 단가 입력 시 expected_amount 재계산 + 배분율 합계 100% 초과 422
- 정산 상태 전이(STANDBY→BILLED→COMPLETED) + 역행/건너뛰기 409 + STAFF 403

주의: conftest가 먼저 import되므로 ASSET_ENC_KEY는 이 모듈 상단에서 주입한다
(services/crypto.py는 키를 호출 시점에 읽는다).
"""

import base64
import os

os.environ["ASSET_ENC_KEY"] = base64.b64encode(b"p2-smoke-test-32byte-key-0123456").decode()

import models  # noqa: E402
from models import AuditLog, Asset, SettlementSnapshot  # noqa: E402
from services import crypto  # noqa: E402

API = "/api/v1"
S = {}  # 테스트 간 공유 상태 (생성된 리소스 id)

PLAINTEXT_PW = "top-secret-pw-1234!"


def _db():
    return models.SessionLocal()


# ---------------------------------------------------------------------------
# 기반: 인증 필수 + 암호화 모듈
# ---------------------------------------------------------------------------
def test_p2_auth_required(client):
    """P2 전 엔드포인트 인증 필수 — 미인증 401."""
    assert client.get(API + "/assets").status_code == 401
    assert client.get(API + "/projects").status_code == 401
    assert client.get(API + "/settlements").status_code == 401
    assert client.post(API + "/assets", json={}).status_code == 401


def test_crypto_roundtrip():
    """AES-256-GCM 왕복 — 암호문은 평문과 다르고 복호화하면 원문."""
    token = crypto.encrypt(PLAINTEXT_PW)
    assert PLAINTEXT_PW not in token
    assert crypto.decrypt(token) == PLAINTEXT_PW


# ---------------------------------------------------------------------------
# 자산 (SCR-04)
# ---------------------------------------------------------------------------
def test_setup_clients(client, staff_headers):
    """P2 테스트용 고객사 2곳 생성."""
    for name, ctype in [("P2운수", "TRANSPORT"), ("P2에너지", "FACILITY")]:
        resp = client.post(
            API + "/clients",
            headers=staff_headers,
            json={"client_type": ctype, "company_name": name},
        )
        assert resp.status_code == 201, resp.text
        S[name] = resp.json()["client_id"]


def test_create_asset_encrypts_credentials(client, staff_headers):
    """자산 등록 — 인증정보는 암호화 저장, 응답·DB 어디에도 평문 미노출."""
    resp = client.post(
        API + "/assets",
        headers=staff_headers,
        json={
            "client_id": S["P2운수"],
            "asset_group": "MOBILITY",
            "asset_type": "EV",
            "quantity": 10,
            "main_spec": "전기버스",
            "telemetry_yn": "Y",
            "agency_name": "한국환경공단",
            "auth_type": "ID_PW",
            "login_id": "fleet-admin",
            "auth_value": PLAINTEXT_PW,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    S["asset_id"] = body["asset_id"]
    # 응답에 평문·암호문 컬럼 자체가 없어야 한다 (has_credentials·auth_type만)
    assert body["has_credentials"] is True
    assert body["auth_type"] == "ID_PW"
    assert "auth_value" not in body
    assert "login_password" not in body
    assert "api_token" not in body
    assert PLAINTEXT_PW not in resp.text

    # DB에도 평문이 아닌 암호문으로 저장
    db = _db()
    try:
        row = db.get(Asset, S["asset_id"])
        assert row.login_password and PLAINTEXT_PW not in row.login_password
        assert row.api_token is None
    finally:
        db.close()


def test_create_asset_none_auth_with_value_422(client, staff_headers):
    """인증 방식 NONE + 인증정보 전달 → 422."""
    resp = client.post(
        API + "/assets",
        headers=staff_headers,
        json={
            "client_id": S["P2운수"],
            "asset_group": "MOBILITY",
            "auth_type": "NONE",
            "auth_value": "should-fail",
        },
    )
    assert resp.status_code == 422


def test_list_assets_filters(client, staff_headers):
    """목록 필터 — 대분류·관제 연동·인증 방식·고객사·검색 + 페이지네이션."""
    # 두 번째 자산 (FACILITY / 관제 미연동 / NONE)
    resp = client.post(
        API + "/assets",
        headers=staff_headers,
        json={
            "client_id": S["P2에너지"],
            "asset_group": "FACILITY",
            "asset_type": "SOLAR",
            "telemetry_yn": "N",
            "auth_type": "NONE",
        },
    )
    assert resp.status_code == 201
    S["asset2_id"] = resp.json()["asset_id"]

    resp = client.get(API + "/assets", params={"asset_category": "MOBILITY"}, headers=staff_headers)
    assert resp.status_code == 200
    assert all(i["asset_group"] == "MOBILITY" for i in resp.json()["items"])

    resp = client.get(API + "/assets", params={"auth_method": "ID_PW"}, headers=staff_headers)
    assert any(i["asset_id"] == S["asset_id"] for i in resp.json()["items"])

    resp = client.get(API + "/assets", params={"monitoring_yn": "N"}, headers=staff_headers)
    assert all(i["telemetry_yn"] == "N" for i in resp.json()["items"])

    resp = client.get(API + "/assets", params={"client_id": S["P2에너지"]}, headers=staff_headers)
    assert resp.json()["total"] == 1

    resp = client.get(API + "/assets", params={"search": "P2운수"}, headers=staff_headers)
    assert any(i["asset_id"] == S["asset_id"] for i in resp.json()["items"])
    # 목록 응답에도 평문 절대 미포함
    assert PLAINTEXT_PW not in resp.text


def test_update_asset(client, staff_headers):
    """자산 수정 — 일반 필드는 인증정보 없이도 수정 가능, auth_value 전달 시 재암호화."""
    resp = client.put(
        API + "/assets/" + S["asset_id"],
        headers=staff_headers,
        json={"quantity": 20, "status": "ERROR"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["quantity"] == 20
    assert resp.json()["has_credentials"] is True  # 인증정보 유지

    resp = client.put(
        API + "/assets/" + S["asset_id"],
        headers=staff_headers,
        json={"auth_value": "new-secret-pw"},
    )
    assert resp.status_code == 200
    assert resp.json()["has_credentials"] is True
    assert "new-secret-pw" not in resp.text


def test_reveal_auth_returns_plaintext_and_audits(client, staff_headers):
    """reveal-auth — 일시 복호화 평문 반환 + tb_audit_log 기록(누가·언제·어떤 자산)."""
    resp = client.post(API + "/assets/" + S["asset_id"] + "/reveal-auth", headers=staff_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["auth_value"] == "new-secret-pw"  # 직전 테스트에서 갱신한 값
    assert body["login_id"] == "fleet-admin"

    db = _db()
    try:
        logs = (
            db.query(AuditLog)
            .filter(AuditLog.action == "REVEAL_AUTH", AuditLog.target_id == S["asset_id"])
            .all()
        )
        assert len(logs) == 1
        assert logs[0].actor_id == "u-staff"
        assert logs[0].target_type == "ASSET"
        # 감사 로그에 인증정보 값 기록 절대 금지 (R2-E6)
        assert not logs[0].new_value
    finally:
        db.close()


def test_reveal_auth_no_credentials_404(client, staff_headers):
    """인증정보가 없는 자산 reveal → 404."""
    resp = client.post(API + "/assets/" + S["asset2_id"] + "/reveal-auth", headers=staff_headers)
    assert resp.status_code == 404


def test_encryption_key_missing_503(client, staff_headers, monkeypatch):
    """키 미설정 시 — 암호화 필요 작업(저장·reveal)만 503, 그 외 CRUD는 정상."""
    monkeypatch.delenv("ASSET_ENC_KEY")

    resp = client.post(API + "/assets/" + S["asset_id"] + "/reveal-auth", headers=staff_headers)
    assert resp.status_code == 503
    assert "ASSET_ENC_KEY" in resp.json()["detail"]

    resp = client.post(
        API + "/assets",
        headers=staff_headers,
        json={
            "client_id": S["P2운수"],
            "asset_group": "MOBILITY",
            "auth_type": "API_KEY",
            "auth_value": "some-token",
        },
    )
    assert resp.status_code == 503

    # 인증정보 없는 CRUD는 정상 동작
    resp = client.get(API + "/assets", headers=staff_headers)
    assert resp.status_code == 200
    resp = client.put(
        API + "/assets/" + S["asset_id"], headers=staff_headers, json={"quantity": 21}
    )
    assert resp.status_code == 200


def test_delete_asset_rbac_and_ok(client, staff_headers, admin_headers):
    """자산 삭제 — STAFF 403, MANAGER 이상 200."""
    assert client.delete(API + "/assets/" + S["asset2_id"], headers=staff_headers).status_code == 403
    assert client.delete(API + "/assets/" + S["asset2_id"], headers=admin_headers).status_code == 200
    assert client.get(API + "/assets/" + S["asset2_id"], headers=staff_headers).status_code == 404


# ---------------------------------------------------------------------------
# 감축 사업 (SCR-06)
# ---------------------------------------------------------------------------
def test_create_project(client, staff_headers):
    """사업 등록 — 단가 미입력 상태로 시작(§10.3 금액 '미정')."""
    resp = client.post(
        API + "/projects",
        headers=staff_headers,
        json={
            "project_name": "P2 전기버스 전환 사업",
            "reg_code": "R-2026-KR-03-000777",
            "project_status": "모니터링",
            "mon_cycle": "분기",
            "expected_credits": 1000,
            "expected_issue_date": "2026-12-01",
            "manager_id": "u-manager",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    S["project_id"] = body["project_id"]
    assert body["price_source"] == "MANUAL"
    assert body["unit_price"] is None
    assert body["expected_issue_date"] == "2026-12-01"  # D-day 계산용 날짜


def test_create_project_invalid_status_422(client, staff_headers):
    resp = client.post(
        API + "/projects",
        headers=staff_headers,
        json={"project_name": "x", "project_status": "WRONG"},
    )
    assert resp.status_code == 422


def test_list_projects_filters(client, staff_headers):
    """목록 — 진행 상태·담당 PM·모니터링 주기 필터 + 참여 고객사 수."""
    resp = client.get(
        API + "/projects",
        params={"project_status": "모니터링", "manager_id": "u-manager", "mon_cycle": "분기"},
        headers=staff_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    item = next(i for i in body["items"] if i["project_id"] == S["project_id"])
    assert item["client_count"] == 0
    assert item["reg_code"] == "R-2026-KR-03-000777"


def test_add_project_client_mapping(client, staff_headers):
    """매핑 등록 — 단가 미입력이면 expected_amount는 null(미정)."""
    resp = client.post(
        API + "/projects/" + S["project_id"] + "/clients",
        headers=staff_headers,
        json={
            "client_id": S["P2운수"],
            "asset_id": S["asset_id"],
            "allocation_ratio": 60,
            "success_fee_rate": 10,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    S["map_id"] = body["map_id"]
    assert body["expected_amount"] is None  # 단가 미정
    assert body["settlement_status"] == "STANDBY"


def test_mapping_asset_of_other_client_422(client, staff_headers):
    """다른 고객사 소유 자산 연결 → 422."""
    resp = client.post(
        API + "/projects/" + S["project_id"] + "/clients",
        headers=staff_headers,
        json={
            "client_id": S["P2에너지"],
            "asset_id": S["asset_id"],  # P2운수 소유
            "allocation_ratio": 10,
            "success_fee_rate": 10,
        },
    )
    assert resp.status_code == 422


def test_allocation_total_over_100_422(client, staff_headers):
    """배분율 합계 100% 초과 → 422 (서버 검증)."""
    resp = client.post(
        API + "/projects/" + S["project_id"] + "/clients",
        headers=staff_headers,
        json={"client_id": S["P2에너지"], "allocation_ratio": 50, "success_fee_rate": 15},
    )
    assert resp.status_code == 422
    assert "배분율" in resp.json()["detail"]


def test_unit_price_input_recalculates(client, staff_headers):
    """단가 수기 입력(§10.3) — 사업 전체 매핑의 expected_amount 재계산."""
    resp = client.put(
        API + "/projects/" + S["project_id"] + "/unit-price",
        headers=staff_headers,
        json={"unit_price": 20000},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["unit_price"] == 20000
    assert body["price_source"] == "MANUAL"
    # 1000 tCO₂ × 60% × 20,000 × 10% = 1,200,000
    row = next(m for m in body["clients"] if m["map_id"] == S["map_id"])
    assert row["expected_amount"] == 1200000
    assert body["allocation_total"] == 60


def test_upsert_mapping_recomputes(client, staff_headers):
    """동일 고객사 매핑 재등록(upsert) — 배분율 변경 시 서버가 금액 재계산."""
    resp = client.post(
        API + "/projects/" + S["project_id"] + "/clients",
        headers=staff_headers,
        json={"client_id": S["P2운수"], "allocation_ratio": 40, "success_fee_rate": 10},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["map_id"] == S["map_id"]  # 신규 생성이 아니라 갱신
    # 1000 × 40% × 20,000 × 10% = 800,000
    assert body["expected_amount"] == 800000


def test_project_detail_with_mappings(client, staff_headers):
    """사업 상세 — 개요 + 참여 고객사 매핑(고객사명·배분율·보수율·금액·정산 상태)."""
    # 두 번째 참여사 (합계 40+30=70 ≤ 100)
    resp = client.post(
        API + "/projects/" + S["project_id"] + "/clients",
        headers=staff_headers,
        json={"client_id": S["P2에너지"], "allocation_ratio": 30, "success_fee_rate": 20},
    )
    assert resp.status_code == 201
    S["map2_id"] = resp.json()["map_id"]

    resp = client.get(API + "/projects/" + S["project_id"], headers=staff_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["clients"]) == 2
    assert body["allocation_total"] == 70
    names = {m["client_name"] for m in body["clients"]}
    assert names == {"P2운수", "P2에너지"}

    # 목록의 참여 고객사 수 반영
    resp = client.get(API + "/projects", headers=staff_headers)
    item = next(i for i in resp.json()["items"] if i["project_id"] == S["project_id"])
    assert item["client_count"] == 2


def test_update_project_recalculates_amounts(client, staff_headers):
    """사업 수정 — 예상 발행량 변경 시에도 매핑 금액 재계산."""
    resp = client.put(
        API + "/projects/" + S["project_id"],
        headers=staff_headers,
        json={"expected_credits": 2000},
    )
    assert resp.status_code == 200, resp.text
    row = next(m for m in resp.json()["clients"] if m["map_id"] == S["map_id"])
    # 2000 × 40% × 20,000 × 10% = 1,600,000
    assert row["expected_amount"] == 1600000


# ---------------------------------------------------------------------------
# 정산 (SCR-07)
# ---------------------------------------------------------------------------
def test_list_settlements(client, staff_headers):
    """정산 목록 — 고객사·사업명·지분율·보수율·예상 정산액·정산 상태."""
    resp = client.get(API + "/settlements", headers=staff_headers)
    assert resp.status_code == 200
    row = next(i for i in resp.json()["items"] if i["map_id"] == S["map_id"])
    assert row["project_name"] == "P2 전기버스 전환 사업"
    assert row["client_name"] == "P2운수"
    assert row["allocation_ratio"] == 40
    assert row["success_fee_rate"] == 10
    assert row["expected_amount"] == 1600000
    assert row["settlement_status"] == "STANDBY"

    resp = client.get(
        API + "/settlements",
        params={"settlement_status": "STANDBY", "project_id": S["project_id"]},
        headers=staff_headers,
    )
    assert resp.json()["total"] == 2

    # 정산 기준월 — STANDBY는 예상 발급월 기준
    resp = client.get(API + "/settlements", params={"period": "2026-12"}, headers=staff_headers)
    assert any(i["map_id"] == S["map_id"] for i in resp.json()["items"])
    resp = client.get(API + "/settlements", params={"period": "1999-01"}, headers=staff_headers)
    assert resp.json()["total"] == 0

    resp = client.get(API + "/settlements", params={"period": "bad"}, headers=staff_headers)
    assert resp.status_code == 422


def test_settlement_change_staff_403(client, staff_headers):
    """정산 상태 변경은 MANAGER 이상(§10.1) — STAFF 403."""
    resp = client.put(
        API + "/settlements/" + S["map_id"] + "/status",
        headers=staff_headers,
        json={"settlement_status": "BILLED"},
    )
    assert resp.status_code == 403


def test_settlement_skip_transition_409(client, admin_headers):
    """STANDBY→COMPLETED 건너뛰기 금지 — 409."""
    resp = client.put(
        API + "/settlements/" + S["map_id"] + "/status",
        headers=admin_headers,
        json={"settlement_status": "COMPLETED"},
    )
    assert resp.status_code == 409


def test_settlement_transitions(client, admin_headers):
    """STANDBY→BILLED→COMPLETED 전이 — 전이 시각 기록 + 서버 계산 금액."""
    resp = client.put(
        API + "/settlements/" + S["map_id"] + "/status",
        headers=admin_headers,
        json={"settlement_status": "BILLED"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["settlement_status"] == "BILLED"
    assert body["billed_at"] is not None
    assert body["expected_amount"] == 1600000  # 항상 서버 계산 값

    resp = client.put(
        API + "/settlements/" + S["map_id"] + "/status",
        headers=admin_headers,
        json={"settlement_status": "COMPLETED", "paid_amount": 1600000, "payment_type": "FULL"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["settlement_status"] == "COMPLETED"
    assert body["completed_at"] is not None
    assert body["paid_amount"] == 1600000

    # 회차 스냅샷(R3-1) 2건 + 감사 로그(SETTLEMENT_CHANGE) 적재
    db = _db()
    try:
        snaps = (
            db.query(SettlementSnapshot)
            .filter(SettlementSnapshot.map_id == S["map_id"])
            .order_by(SettlementSnapshot.seq.asc())
            .all()
        )
        assert [s.action for s in snaps] == ["BILLED", "COMPLETED"]
        logs = (
            db.query(AuditLog)
            .filter(AuditLog.action == "SETTLEMENT_CHANGE", AuditLog.target_id == S["map_id"])
            .all()
        )
        assert len(logs) == 2
    finally:
        db.close()


def test_settlement_reverse_409(client, admin_headers):
    """역행 금지 — COMPLETED→BILLED 409."""
    resp = client.put(
        API + "/settlements/" + S["map_id"] + "/status",
        headers=admin_headers,
        json={"settlement_status": "BILLED"},
    )
    assert resp.status_code == 409


def test_settled_mapping_cannot_be_deleted(client, staff_headers):
    """정산이 진행된 매핑은 해제 불가 — 409."""
    resp = client.delete(
        API + "/projects/" + S["project_id"] + "/clients/" + S["map_id"],
        headers=staff_headers,
    )
    assert resp.status_code == 409


def test_delete_mapping_and_project_rbac(client, staff_headers, admin_headers):
    """매핑 해제(STANDBY) 200 · 사업 삭제는 MANAGER 이상, 정산 진행 시 409."""
    resp = client.delete(
        API + "/projects/" + S["project_id"] + "/clients/" + S["map2_id"],
        headers=staff_headers,
    )
    assert resp.status_code == 200

    # 사업 삭제 — STAFF 403 (client.delete는 MANAGER 이상)
    assert client.delete(API + "/projects/" + S["project_id"], headers=staff_headers).status_code == 403
    # COMPLETED 매핑이 남아 있어 관리자도 409
    assert client.delete(API + "/projects/" + S["project_id"], headers=admin_headers).status_code == 409

    # 정산 이력이 없는 사업은 관리자가 삭제 가능
    resp = client.post(
        API + "/projects", headers=staff_headers, json={"project_name": "삭제용 사업"}
    )
    pid = resp.json()["project_id"]
    assert client.delete(API + "/projects/" + pid, headers=admin_headers).status_code == 200
    assert client.get(API + "/projects/" + pid, headers=staff_headers).status_code == 404
