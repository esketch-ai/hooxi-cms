"""정산 확정(freeze) — P4 SCR-07.

검증: Σ ProjectVehicle.expected_payout 동결(confirmed_amount)·전건 None→409(미산정)·중복 확정 409·
확정 후 차량 expected_payout이 바뀌어도 confirmed_amount 불변(동결 불변식, R3-1)·확정 스냅샷(seq=1).
"""

import models

API = "/api/v1"
PROJECTS = API + "/projects"
SETTLEMENTS = API + "/settlements"


# ── 시드 헬퍼 ────────────────────────────────────────────────────────────────
def _mk_client(client, headers, tag):
    r = client.post(API + "/clients", headers=headers,
                    json={"client_type": "TRANSPORT", "company_name": "확정운수" + tag})
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


def _add_vehicle(client, headers, pid, per_year, cid):
    r = client.post(f"{PROJECTS}/{pid}/vehicles", headers=headers,
                    json=_capped_vehicle(per_year, cid))
    assert r.status_code == 201, r.text
    return r.json()["vehicle_id"]


def _set_payout(client, headers, pid):
    r = client.put(f"{PROJECTS}/{pid}/payout-params", headers=headers,
                   json={"max_payment": 1200000, "approved_at": "2016-02-01"})
    assert r.status_code == 200, r.text


def _db_sums(client_id, project_id):
    """확정 시점 Σ expected_payout·Σ effective_reduction·대수 — 기대치 정본."""
    db = models.SessionLocal()
    try:
        vs = (db.query(models.ProjectVehicle)
              .filter(models.ProjectVehicle.client_id == client_id,
                      models.ProjectVehicle.project_id == project_id).all())
        pay = [float(v.expected_payout) for v in vs if v.expected_payout is not None]
        eff = [float(v.effective_reduction) for v in vs if v.effective_reduction is not None]
        return (round(sum(pay), 2) if pay else None,
                round(sum(eff), 3) if eff else None, len(vs))
    finally:
        db.close()


# ── 1) 확정 freeze — Σ expected_payout 동결 + 확정 스냅샷 ─────────────────────
def test_confirm_freezes_sum(client, manager_headers):
    cid = _mk_client(client, manager_headers, "A")
    pid = _mk_project(client, manager_headers, "확정사업A")
    _add_vehicle(client, manager_headers, pid, 30, cid)
    _add_vehicle(client, manager_headers, pid, 30, cid)
    _set_payout(client, manager_headers, pid)
    exp_pay, exp_eff, n = _db_sums(cid, pid)
    assert exp_pay is not None and n == 2

    r = client.post(SETTLEMENTS + "/confirm", headers=manager_headers,
                    json={"client_id": cid, "project_id": pid})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "CONFIRMED"
    assert abs(body["confirmed_amount"] - exp_pay) < 0.5
    assert body["vehicle_count"] == 2
    assert abs(body["effective_reduction"] - exp_eff) < 0.5
    assert body["confirmed_at"] and body["confirmed_by"]
    sid = body["settlement_id"]

    # 확정 스냅샷(seq=1, action=CONFIRMED, 동결 금액)
    snaps = client.get(f"{SETTLEMENTS}/{sid}/snapshots", headers=manager_headers).json()
    assert snaps["total"] == 1
    s0 = snaps["items"][0]
    assert s0["seq"] == 1 and s0["action"] == "CONFIRMED"
    assert abs(s0["amount"] - exp_pay) < 0.5
    assert s0["vehicle_count"] == 2


# ── 2) 전건 None(예상지급액 미산정) → 409 ────────────────────────────────────
def test_confirm_all_none_409(client, manager_headers):
    cid = _mk_client(client, manager_headers, "N")
    pid = _mk_project(client, manager_headers, "확정미산정N")
    _add_vehicle(client, manager_headers, pid, 30, cid)
    _add_vehicle(client, manager_headers, pid, 30, cid)
    # payout-params 미설정 → expected_payout 전건 None

    r = client.post(SETTLEMENTS + "/confirm", headers=manager_headers,
                    json={"client_id": cid, "project_id": pid})
    assert r.status_code == 409, r.text
    assert "미산정" in r.json()["detail"]
    # 헤더·스냅샷 미생성(확정 반려)
    lst = client.get(SETTLEMENTS, headers=manager_headers,
                     params={"client_id": cid}).json()
    assert lst["total"] == 0


# ── 3) 중복 확정 → 409 ───────────────────────────────────────────────────────
def test_confirm_duplicate_409(client, manager_headers):
    cid = _mk_client(client, manager_headers, "D")
    pid = _mk_project(client, manager_headers, "확정중복D")
    _add_vehicle(client, manager_headers, pid, 30, cid)
    _set_payout(client, manager_headers, pid)

    r1 = client.post(SETTLEMENTS + "/confirm", headers=manager_headers,
                     json={"client_id": cid, "project_id": pid})
    assert r1.status_code == 201, r1.text
    r2 = client.post(SETTLEMENTS + "/confirm", headers=manager_headers,
                     json={"client_id": cid, "project_id": pid})
    assert r2.status_code == 409, r2.text
    assert "중복" in r2.json()["detail"] or "이미" in r2.json()["detail"]


# ── 3b) period 미지정 → '' sentinel 저장 (NULL distinct 함정 회피, DB 백스톱) ──
def test_confirm_period_stored_as_empty_sentinel(client, manager_headers):
    cid = _mk_client(client, manager_headers, "S")
    pid = _mk_project(client, manager_headers, "확정sentinelS")
    _add_vehicle(client, manager_headers, pid, 30, cid)
    _set_payout(client, manager_headers, pid)

    r = client.post(SETTLEMENTS + "/confirm", headers=manager_headers,
                    json={"client_id": cid, "project_id": pid})
    assert r.status_code == 201, r.text
    sid = r.json()["settlement_id"]
    db = models.SessionLocal()
    try:
        got = db.get(models.Settlement, sid)
        assert got.period == ""  # None이 아닌 '' sentinel — uq(client,project,'')가 중복 강제
    finally:
        db.close()


# ── 3c) vehicle_count·effective_reduction grain — 기여 차량(payout non-null) 기준 ──
def test_confirm_count_matches_contributing(client, manager_headers):
    cid = _mk_client(client, manager_headers, "G")
    pid = _mk_project(client, manager_headers, "확정기여G")
    _add_vehicle(client, manager_headers, pid, 30, cid)
    v2 = _add_vehicle(client, manager_headers, pid, 30, cid)
    _set_payout(client, manager_headers, pid)

    # 한 차량의 예상지급액만 None으로 강제 — confirmed_amount 기여 집합에서 제외되어야
    db = models.SessionLocal()
    try:
        v1_eff, = (float(v.effective_reduction)
                   for v in [db.query(models.ProjectVehicle)
                             .filter(models.ProjectVehicle.project_id == pid,
                                     models.ProjectVehicle.vehicle_id != v2).one()])
        v = db.get(models.ProjectVehicle, v2)
        v.expected_payout = None
        db.commit()
    finally:
        db.close()

    r = client.post(SETTLEMENTS + "/confirm", headers=manager_headers,
                    json={"client_id": cid, "project_id": pid})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["vehicle_count"] == 1  # payout non-null 차량만(전 차량 2 아님)
    assert abs(body["effective_reduction"] - v1_eff) < 0.5  # 동일 기여 집합 기준


# ── 4) 동결 불변식 — 확정 후 expected_payout 변경돼도 confirmed_amount 불변 ────
def test_freeze_invariant(client, manager_headers):
    cid = _mk_client(client, manager_headers, "F")
    pid = _mk_project(client, manager_headers, "확정불변F")
    vid = _add_vehicle(client, manager_headers, pid, 30, cid)
    _set_payout(client, manager_headers, pid)

    r = client.post(SETTLEMENTS + "/confirm", headers=manager_headers,
                    json={"client_id": cid, "project_id": pid})
    assert r.status_code == 201, r.text
    sid = r.json()["settlement_id"]
    frozen = r.json()["confirmed_amount"]
    assert frozen is not None

    # 확정 후 차량 예상지급액을 직접 크게 변경(정본 파생값 우회) — 동결값은 불변이어야
    db = models.SessionLocal()
    try:
        v = db.get(models.ProjectVehicle, vid)
        v.expected_payout = float(v.expected_payout or 0) + 9_000_000
        db.commit()
    finally:
        db.close()

    got = client.get(SETTLEMENTS, headers=manager_headers,
                     params={"client_id": cid}).json()["items"][0]
    assert abs(got["confirmed_amount"] - frozen) < 0.01  # 동결 불변식
    # 스냅샷 정본도 불변
    s0 = client.get(f"{SETTLEMENTS}/{sid}/snapshots",
                    headers=manager_headers).json()["items"][0]
    assert abs(s0["amount"] - frozen) < 0.01
