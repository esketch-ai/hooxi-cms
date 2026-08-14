"""정산 상태전이 — P4 SCR-07.

검증: CONFIRMED→BILLED→COMPLETED 정방향·역행/건너뛰기/종단전이 409·낙관적 동시성 409·
COMPLETED paid_amount=confirmed_amount 승계(재계산 없음)·청구취소 BILLED→CONFIRMED(ADMIN만·사유 필수·
REVERTED 이력)·인가(STAFF 전이403/조회200·OBSERVER·외부역할 403·MANAGER 통과)·감사(금액 원문 미기록)·
스냅샷 append-only.
"""

from sqlalchemy import text as sa_text

import models
from routers import common as rcommon

API = "/api/v1"
PROJECTS = API + "/projects"
SETTLEMENTS = API + "/settlements"


# ── 시드 헬퍼 ────────────────────────────────────────────────────────────────
def _mk_client(client, headers, tag):
    r = client.post(API + "/clients", headers=headers,
                    json={"client_type": "TRANSPORT", "company_name": "전이운수" + tag})
    assert r.status_code == 201, r.text
    return r.json()["client_id"]


def _mk_project(client, headers, name):
    r = client.post(PROJECTS, headers=headers,
                    json={"project_name": name, "project_status": "기획"})
    assert r.status_code == 201, r.text
    return r.json()["project_id"]


def _capped_vehicle(per_year, cid):
    p = {"registered_at": "2016-01-01", "client_id": cid}
    for i in range(1, 9):
        p["reduction_y{0}".format(i)] = per_year
    return p


def _confirm(client, headers, tag):
    """확정된 정산 1건 생성 → settlement_id 반환."""
    cid = _mk_client(client, headers, tag)
    pid = _mk_project(client, headers, "전이사업" + tag)
    r = client.post(f"{PROJECTS}/{pid}/vehicles", headers=headers,
                    json=_capped_vehicle(30, cid))
    assert r.status_code == 201, r.text
    r = client.put(f"{PROJECTS}/{pid}/payout-params", headers=headers,
                   json={"max_payment": 1200000, "approved_at": "2016-02-01"})
    assert r.status_code == 200, r.text
    r = client.post(SETTLEMENTS + "/confirm", headers=headers,
                    json={"client_id": cid, "project_id": pid})
    assert r.status_code == 201, r.text
    return r.json()["settlement_id"]


def _put_status(client, headers, sid, target, reason=None):
    body = {"target_status": target}
    if reason is not None:
        body["reason"] = reason
    return client.put(f"{SETTLEMENTS}/{sid}/status", headers=headers, json=body)


def _login_role(client, user_id, email, role, status="ACTIVE"):
    db = models.SessionLocal()
    try:
        u = db.get(models.User, user_id)
        if u is None:
            u = models.User(user_id=user_id, email=email, name=email.split("@")[0])
            db.add(u)
        u.role = role
        u.status = status
        db.commit()
    finally:
        db.close()
    tok = client.post(API + "/auth/dev-login", json={"email": email})
    assert tok.status_code == 200, tok.text
    return {"Authorization": "Bearer {0}".format(tok.json()["access_token"])}


# ── 1) 정방향 CONFIRMED→BILLED→COMPLETED + paid_amount 승계 ──────────────────
def test_forward_path_and_carry(client, manager_headers):
    sid = _confirm(client, manager_headers, "FW")
    confirmed = client.get(SETTLEMENTS, headers=manager_headers).json()
    frozen = next(i for i in confirmed["items"] if i["settlement_id"] == sid)["confirmed_amount"]

    r = _put_status(client, manager_headers, sid, "BILLED")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "BILLED" and r.json()["billed_at"]

    r = _put_status(client, manager_headers, sid, "COMPLETED")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "COMPLETED" and body["completed_at"]
    # 재계산 금지 — paid_amount = confirmed_amount 승계
    assert abs(body["paid_amount"] - frozen) < 0.01

    # 스냅샷 append-only: seq 1(CONFIRMED)·2(BILLED)·3(COMPLETED), 금액 동결 승계
    snaps = client.get(f"{SETTLEMENTS}/{sid}/snapshots", headers=manager_headers).json()
    seqs = [(s["seq"], s["action"]) for s in snaps["items"]]
    assert seqs == [(1, "CONFIRMED"), (2, "BILLED"), (3, "COMPLETED")]
    for s in snaps["items"]:
        assert abs(s["amount"] - frozen) < 0.01


# ── 2) 역행·건너뛰기·종단 전이 → 409 ────────────────────────────────────────
def test_illegal_transitions_409(client, manager_headers):
    # 건너뛰기: CONFIRMED→COMPLETED 금지
    sid = _confirm(client, manager_headers, "SKIP")
    assert _put_status(client, manager_headers, sid, "COMPLETED").status_code == 409

    # 종단: COMPLETED 이후 어떤 전이도 금지
    sid2 = _confirm(client, manager_headers, "TERM")
    assert _put_status(client, manager_headers, sid2, "BILLED").status_code == 200
    assert _put_status(client, manager_headers, sid2, "COMPLETED").status_code == 200
    assert _put_status(client, manager_headers, sid2, "BILLED").status_code == 409  # 역행
    assert _put_status(client, manager_headers, sid2, "CONFIRMED").status_code == 409


# ── 3) 낙관적 동시성 — 스냅샷 이후 상태 변경되면 409(phantom 전이 차단) ────────
def test_optimistic_concurrency_409(client, manager_headers, monkeypatch):
    sid = _confirm(client, manager_headers, "CC")
    orig = rcommon.get_or_404
    fired = {"done": False}

    def stale_get(db, m, pk, label):
        obj = orig(db, m, pk, label)
        if m is models.Settlement and pk == sid and not fired["done"]:
            fired["done"] = True
            # 다른 사용자가 먼저 BILLED로 전이한 상황 주입(같은 커넥션)
            db.execute(sa_text("UPDATE tb_settlement SET status='BILLED' "
                               "WHERE settlement_id=:s"), {"s": sid})
        return obj

    monkeypatch.setattr(rcommon, "get_or_404", stale_get)
    # 읽은 상태(CONFIRMED) 기준 BILLED 전이 시도 → 조건부 UPDATE 0건 → 409
    r = _put_status(client, manager_headers, sid, "BILLED")
    assert r.status_code == 409, r.text
    assert "다른 사용자" in r.json()["detail"]


# ── 4) 청구취소 BILLED→CONFIRMED — ADMIN만·사유 필수·REVERTED 이력 ────────────
def test_revert_admin_only(client, manager_headers, admin_headers):
    sid = _confirm(client, manager_headers, "RV")
    assert _put_status(client, manager_headers, sid, "BILLED").status_code == 200

    # MANAGER 청구취소 → 403(더 좁은 게이트)
    assert _put_status(client, manager_headers, sid, "CONFIRMED",
                       reason="정정").status_code == 403
    # ADMIN 사유 없이 → 400
    assert _put_status(client, admin_headers, sid, "CONFIRMED").status_code == 400
    # ADMIN 사유 포함 → 200, CONFIRMED 복귀 + billed_at 클리어
    r = _put_status(client, admin_headers, sid, "CONFIRMED", reason="오청구 정정")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "CONFIRMED" and r.json()["billed_at"] is None

    # REVERTED 스냅샷(사유 포함) append-only 이력
    snaps = client.get(f"{SETTLEMENTS}/{sid}/snapshots", headers=admin_headers).json()
    rev = [s for s in snaps["items"] if s["action"] == "REVERTED"]
    assert len(rev) == 1 and rev[0]["reason"] == "오청구 정정"
    # 취소 후 재청구 가능(CONFIRMED→BILLED)
    assert _put_status(client, admin_headers, sid, "BILLED").status_code == 200


# ── 5) 인가 — STAFF·OBSERVER·외부역할 격리 ───────────────────────────────────
def test_authz_transitions(client, manager_headers, admin_headers, staff_headers):
    sid = _confirm(client, manager_headers, "AZ")

    # STAFF: 전이·확정 403, 조회는 200
    assert _put_status(client, staff_headers, sid, "BILLED").status_code == 403
    assert client.post(SETTLEMENTS + "/confirm", headers=staff_headers,
                       json={"client_id": "x", "project_id": "y"}).status_code == 403
    assert client.get(SETTLEMENTS, headers=staff_headers).status_code == 200
    assert client.get(f"{SETTLEMENTS}/{sid}/snapshots",
                      headers=staff_headers).status_code == 200

    # OBSERVER: 정산 API 전부 403(화이트리스트 밖 + settlement.change 미보유)
    obs = _login_role(client, "u-st-obs", "st-obs@hooxipartners.com", "OBSERVER")
    assert client.get(SETTLEMENTS, headers=obs).status_code == 403
    assert _put_status(client, obs, sid, "BILLED").status_code == 403

    # 외부역할: 원천 403
    partner = _login_role(client, "u-st-partner", "st-partner@carrier.example", "PARTNER")
    investor = _login_role(client, "u-st-investor", "st-investor@fund.example", "INVESTOR")
    assert client.get(SETTLEMENTS, headers=partner).status_code == 403
    assert _put_status(client, investor, sid, "BILLED").status_code == 403

    # MANAGER: 정방향 통과
    assert _put_status(client, manager_headers, sid, "BILLED").status_code == 200
    assert _put_status(client, manager_headers, sid, "COMPLETED").status_code == 200

    # 미인증 401
    assert client.get(SETTLEMENTS).status_code == 401


# ── 6) 감사 — 각 전이 SETTLEMENT_CHANGE, new_value에 금액 원문 없음(R2-E6) ────
def test_audit_no_amount(client, manager_headers):
    sid = _confirm(client, manager_headers, "AU")
    frozen = next(i for i in client.get(SETTLEMENTS, headers=manager_headers).json()["items"]
                  if i["settlement_id"] == sid)["confirmed_amount"]
    _put_status(client, manager_headers, sid, "BILLED")
    _put_status(client, manager_headers, sid, "COMPLETED")

    db = models.SessionLocal()
    try:
        logs = (db.query(models.AuditLog)
                .filter(models.AuditLog.action == "SETTLEMENT_CHANGE",
                        models.AuditLog.target_id == sid)
                .order_by(models.AuditLog.created_at.asc()).all())
        # 확정 + BILLED + COMPLETED = 3건, target_type=SETTLEMENT
        assert len(logs) == 3
        assert all(x.target_type == "SETTLEMENT" for x in logs)
        news = [x.new_value for x in logs]
        assert news == ["CONFIRMED", "BILLED", "COMPLETED"]  # 상태만
        # 금액 원문 미기록(R2-E6)
        for x in logs:
            assert str(int(frozen)) not in (x.new_value or "")
            assert str(int(frozen)) not in (x.old_value or "")
    finally:
        db.close()
