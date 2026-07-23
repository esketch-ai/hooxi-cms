"""청구 취소 (POST /settlements/{map_id}/revert) — BILLED→STANDBY.

검증 포인트:
- ADMIN 전용: STAFF·MANAGER(정방향 전이는 가능)도 취소는 403
- BILLED에서만 취소 가능 — STANDBY/COMPLETED(종단)는 409
- 취소 시 STANDBY 복귀 + billed_at 초기화, 재청구 시 금액 재계산
- REVERTED 스냅샷(append-only)에 취소 직전 청구 금액 승계 → 이력 보존
"""

API = "/api/v1"
S = {}  # 테스트 간 공유 상태


def _login(client, email):
    r = client.post(API + "/auth/dev-login", json={"email": email})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def _row(client, headers, map_id):
    r = client.get(API + "/settlements", headers=headers)
    assert r.status_code == 200, r.text
    return next(i for i in r.json()["items"] if i["map_id"] == map_id)


def _bill(client, headers):
    r = client.put(
        API + "/settlements/" + S["map"] + "/status", headers=headers,
        json={"settlement_status": "BILLED"},
    )
    assert r.status_code == 200, r.text


def test_setup(client, staff_headers):
    """고객사 + 사업(1000 tCO₂ × 10,000) + 매핑(50%·10%) = 500,000."""
    r = client.post(
        API + "/clients", headers=staff_headers,
        json={"client_type": "TRANSPORT", "company_name": "청구취소운수"},
    )
    assert r.status_code == 201, r.text
    cid = r.json()["client_id"]
    r = client.post(
        API + "/projects", headers=staff_headers,
        json={"project_name": "청구취소 검증 사업", "project_status": "모니터링",
              "expected_credits": 1000, "unit_price": 10000, "manager_id": "u-manager"},
    )
    assert r.status_code == 201, r.text
    S["project_id"] = r.json()["project_id"]
    r = client.post(
        API + "/projects/" + S["project_id"] + "/clients", headers=staff_headers,
        json={"client_id": cid, "allocation_ratio": 50, "success_fee_rate": 10},
    )
    assert r.status_code == 201, r.text
    S["map"] = r.json()["map_id"]
    assert _row(client, staff_headers, S["map"])["expected_amount"] == 500000


def test_revert_requires_admin(client, admin_headers, staff_headers):
    _bill(client, admin_headers)
    # STAFF 거부
    assert client.post(
        API + "/settlements/" + S["map"] + "/revert", headers=staff_headers, json={}
    ).status_code == 403
    # MANAGER도 거부 — 정방향 전이(청구·입금)는 가능하지만 청구 취소는 ADMIN 전용
    mgr = _login(client, "manager@hooxipartners.com")
    assert client.post(
        API + "/settlements/" + S["map"] + "/revert", headers=mgr, json={}
    ).status_code == 403
    # 여전히 BILLED (권한 실패는 상태 불변)
    assert _row(client, admin_headers, S["map"])["settlement_status"] == "BILLED"


def test_revert_billed_to_standby(client, admin_headers):
    r = client.post(
        API + "/settlements/" + S["map"] + "/revert", headers=admin_headers,
        json={"reason": "오발행 정정"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["settlement_status"] == "STANDBY"
    assert body["billed_at"] is None

    # REVERTED 스냅샷 적재 — 취소 직전 청구 금액(500,000) 승계
    snaps = client.get(
        API + "/settlements/" + S["map"] + "/snapshots", headers=admin_headers
    ).json()["items"]
    assert snaps[-1]["action"] == "REVERTED"
    assert snaps[-1]["amount"] == 500000

    # 재청구 가능 — 금액 재계산 후 다시 BILLED
    _bill(client, admin_headers)
    assert _row(client, admin_headers, S["map"])["settlement_status"] == "BILLED"


def test_revert_completed_blocked_409(client, admin_headers):
    # 재청구된 건을 입금 완료(COMPLETED, 종단) 처리 → 취소 시도 시 409
    r = client.put(
        API + "/settlements/" + S["map"] + "/status", headers=admin_headers,
        json={"settlement_status": "COMPLETED", "paid_amount": 500000},
    )
    assert r.status_code == 200, r.text
    assert client.post(
        API + "/settlements/" + S["map"] + "/revert", headers=admin_headers, json={}
    ).status_code == 409
    # 상태 불변(COMPLETED 유지)
    assert _row(client, admin_headers, S["map"])["settlement_status"] == "COMPLETED"
