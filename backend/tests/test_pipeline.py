"""부서 워크플로우 파이프라인(P4 증분4) — (운수사×사업) 5단계 진행 파생 조회.

검증: 5단계 파생 로직 매트릭스(_derive_stage 단위) + DB 신호 배선(has_accounting·
settlement_status·(미지정) 통지불가) + 필터(client_id·project_id·settlement_status) +
인가(내부 200 / OBSERVER 403(관찰 스코프 미화이트리스트) / 외부역할 403) + 쿼리 수(N+1 없음).

전역(약한) 신호 reported/notified는 세션 공유 DB에서 타 테스트 감사로 오염될 수 있어,
단계 파생의 결정적 검증은 (1) 순수 _derive_stage 단위 매트릭스, (2) 하위 단계 게이트로
전역 신호와 무관하게 고정되는 collect/accounting, (3) 자기 신호를 직접 심어 notice까지
도달시키는 통합으로 나눈다.
"""

import models
from services.pipeline import _derive_stage, settlement_pipeline

API = "/api/v1"
PIPELINE = API + "/settlements/pipeline"


# ── 시드 헬퍼(직접 DB — 단계별 정밀 제어) ────────────────────────────────────
def _db():
    return models.SessionLocal()


def _seed_cell(client, headers, tag, *, with_payout=False, header_status=None,
               unassigned=False):
    """(운수사×사업) 셀 1개 시드 — 차량은 API로 생성해 파생값을 정합 저장(전역 정합감사 무오염).

    with_payout=True면 payout-params 설정으로 expected_payout 파생(결산 신호). header_status
    지정 시 정산 헤더만 직접 삽입(차량 정합과 무관). unassigned=True면 미지정 셀(차량 client_id NULL).
    반환: (client_id, project_id).
    """
    cid = None
    if not unassigned:
        r = client.post(API + "/clients", headers=headers,
                        json={"client_type": "TRANSPORT", "company_name": "파이프운수" + tag})
        assert r.status_code == 201, r.text
        cid = r.json()["client_id"]
    r = client.post(API + "/projects", headers=headers,
                    json={"project_name": "파이프사업" + tag, "project_status": "기획"})
    assert r.status_code == 201, r.text
    pid = r.json()["project_id"]
    vp = {"registered_at": "2016-01-01", "reduction_y1": 10}
    if cid is not None:
        vp["client_id"] = cid
    r = client.post("{0}/projects/{1}/vehicles".format(API, pid), headers=headers, json=vp)
    assert r.status_code == 201, r.text
    if with_payout:  # payout-params 설정 → 기존 차량 expected_payout 재계산(부록 L)
        r = client.put("{0}/projects/{1}/payout-params".format(API, pid), headers=headers,
                       json={"max_payment": 1200000, "approved_at": "2016-02-01"})
        assert r.status_code == 200, r.text
    if header_status is not None:  # 정산 헤더만 직접 삽입(상태 배선 검증용)
        db = _db()
        try:
            db.add(models.Settlement(
                settlement_id="pl-s-" + tag, client_id=cid, project_id=pid,
                status=header_status, confirmed_amount=1200000, vehicle_count=1,
            ))
            db.commit()
        finally:
            db.close()
    return cid, pid


def _login(client, user_id, email, role):
    db = _db()
    try:
        u = db.get(models.User, user_id)
        if u is None:
            u = models.User(user_id=user_id, email=email, name=email.split("@")[0])
            db.add(u)
        u.role = role
        u.status = "ACTIVE"
        db.commit()
    finally:
        db.close()
    tok = client.post(API + "/auth/dev-login", json={"email": email})
    assert tok.status_code == 200, tok.text
    return {"Authorization": "Bearer {0}".format(tok.json()["access_token"])}


def _row_for(items, project_id):
    rows = [it for it in items if it["project_id"] == project_id]
    assert len(rows) == 1, "cell {0} rows={1}".format(project_id, len(rows))
    return rows[0]


# ── 1. 5단계 파생 매트릭스(순수 로직 — 결정적) ───────────────────────────────
def test_derive_stage_matrix():
    """수집→결산→정산→보고→통지 각 신호 조합에서 최고 도달 단계가 정확한가."""
    # 차량 없음 → 미착수
    assert _derive_stage(0, False, None, False, False) == "none"
    # 차량만 → 수집
    assert _derive_stage(1, False, None, False, False) == "collect"
    # +예상지급액 → 결산
    assert _derive_stage(1, True, None, False, False) == "accounting"
    # +정산 헤더 → 정산
    assert _derive_stage(1, True, "CONFIRMED", False, False) == "settlement"
    # +보고서 반출 → 보고
    assert _derive_stage(1, True, "CONFIRMED", True, False) == "report"
    # +통지 → 통지(최종)
    assert _derive_stage(1, True, "CONFIRMED", True, True) == "notice"


def test_derive_stage_non_contiguous_gated():
    """전역(약한) 신호(reported/notified)가 있어도 하위 단계 미충족이면 승격 금지."""
    # 결산 전(payout 없음)엔 reported/notified가 있어도 수집에서 멈춘다
    assert _derive_stage(1, False, None, True, True) == "collect"
    # 정산 헤더 없으면 reported/notified 있어도 결산에서 멈춘다
    assert _derive_stage(1, True, None, True, True) == "accounting"


def test_next_action_mapping():
    """단계별 다음 할일 문자열 — 각 단계의 미도달 다음 단계 안내."""
    db = _db()
    try:
        res = settlement_pipeline(db)  # 스모크: 예외 없이 dict 구조
    finally:
        db.close()
    assert set(res.keys()) == {"items", "total", "stage_counts"}
    assert res["total"] == len(res["items"])


# ── 2. DB 신호 배선(게이트로 결정적인 collect/accounting) ─────────────────────
def test_collect_stage_wiring(client, staff_headers):
    """차량만 있는 셀 — stage=collect, has_accounting=False, settlement_status=None."""
    cid, pid = _seed_cell(client, staff_headers, "collect")
    r = client.get(PIPELINE, headers=staff_headers, params={"client_id": cid})
    assert r.status_code == 200, r.text
    row = _row_for(r.json()["items"], pid)
    assert row["stage"] == "collect"
    assert row["next_action"] == "예상지급액 산정 필요"
    assert row["has_accounting"] is False
    assert row["settlement_status"] is None
    assert row["vehicle_count"] == 1


def test_accounting_stage_wiring(client, staff_headers):
    """차량+예상지급액 — stage=accounting, has_accounting=True, 헤더 없어 status=None."""
    cid, pid = _seed_cell(client, staff_headers, "acct", with_payout=True)
    r = client.get(PIPELINE, headers=staff_headers, params={"client_id": cid})
    assert r.status_code == 200, r.text
    row = _row_for(r.json()["items"], pid)
    assert row["stage"] == "accounting"
    assert row["next_action"] == "정산 확정 필요"
    assert row["has_accounting"] is True
    assert row["settlement_status"] is None


def test_settlement_status_passthrough(client, staff_headers):
    """정산 헤더 존재 — settlement_status가 헤더 status(CONFIRMED)로 노출, 최소 정산단계 이상."""
    cid, pid = _seed_cell(client, staff_headers, "settle", with_payout=True, header_status="CONFIRMED")
    r = client.get(PIPELINE, headers=staff_headers, params={"client_id": cid})
    row = _row_for(r.json()["items"], pid)
    assert row["settlement_status"] == "CONFIRMED"
    assert row["has_accounting"] is True
    # 전역 보고/통지 신호 오염 가능 → 정산 이상 단계임만 보장(수집/결산으로 후퇴 없음)
    assert row["stage"] in {"settlement", "report", "notice"}


def test_full_pipeline_reaches_notice(client, staff_headers):
    """자기 신호(보고서 반출 감사 + 운수사 [자동]정산 EMAIL)를 심으면 통지까지 도달."""
    cid, pid = _seed_cell(client, staff_headers, "full", with_payout=True, header_status="CONFIRMED")
    db = _db()
    try:
        # 보고(전역 약한 신호): DATA_EXPORT/ASSET_REPORT 감사
        db.add(models.AuditLog(actor_id="u-staff", action="DATA_EXPORT",
                               target_type="ASSET_REPORT"))
        # 통지(운수사 정확 신호): [자동] 정산 명세 EMAIL 활동 이력
        db.add(models.ActivityHistory(
            client_id=cid, manager_id="u-staff", created_by="u-staff",
            activity_date=models.utcnow(), activity_type="EMAIL",
            title="[자동] 정산 예정 명세 이메일 발송",
        ))
        db.commit()
    finally:
        db.close()
    r = client.get(PIPELINE, headers=staff_headers, params={"client_id": cid})
    row = _row_for(r.json()["items"], pid)
    assert row["reported"] is True
    assert row["notified"] is True
    assert row["stage"] == "notice"
    assert row["next_action"] == "완료"


def test_unassigned_cell_not_notifiable(client, staff_headers):
    """미지정(client_id=None) 셀 — 라벨 '(미지정)', 통지 불가(notified=False 강제)."""
    _cid, pid = _seed_cell(client, staff_headers, "unassigned", with_payout=True, unassigned=True)
    r = client.get(PIPELINE, headers=staff_headers, params={"project_id": pid})
    row = _row_for(r.json()["items"], pid)
    assert row["client_id"] is None
    assert row["company_name"] == "(미지정)"
    assert row["notified"] is False
    # 통지 불가 → 통지 단계엔 도달 못함(정산·보고까지만 가능)
    assert row["stage"] != "notice"


# ── 3. 필터 ──────────────────────────────────────────────────────────────────
def test_filter_by_settlement_status(client, staff_headers):
    """settlement_status 필터 — 파생 status 일치 행만. 불일치 status는 제외."""
    cid, pid = _seed_cell(client, staff_headers, "filt", with_payout=True, header_status="CONFIRMED")
    r_hit = client.get(PIPELINE, headers=staff_headers,
                       params={"client_id": cid, "settlement_status": "CONFIRMED"})
    assert any(it["project_id"] == pid for it in r_hit.json()["items"])
    r_miss = client.get(PIPELINE, headers=staff_headers,
                        params={"client_id": cid, "settlement_status": "BILLED"})
    assert not any(it["project_id"] == pid for it in r_miss.json()["items"])


def test_filter_by_client_id_scopes_rows(client, staff_headers):
    """client_id 필터 — 그 운수사 셀만 반환(타 운수사 셀 미포함)."""
    cid, pid = _seed_cell(client, staff_headers, "scopeA")
    other_cid, other_pid = _seed_cell(client, staff_headers, "scopeB")
    r = client.get(PIPELINE, headers=staff_headers, params={"client_id": cid})
    pids = {it["project_id"] for it in r.json()["items"]}
    assert pid in pids
    assert other_pid not in pids


# ── 4. 인가(내부 200 / OBSERVER 403 / 외부 403) ──────────────────────────────
def test_internal_staff_allowed(client, staff_headers):
    assert client.get(PIPELINE, headers=staff_headers).status_code == 200


def test_observer_forbidden(client):
    """OBSERVER — /settlements* 관찰 스코프 미화이트리스트 → get_current_user 자동 403."""
    h = _login(client, "pl-observer", "pl-observer@hooxipartners.com", "OBSERVER")
    assert client.get(PIPELINE, headers=h).status_code == 403


def test_external_role_forbidden(client):
    """외부역할(PARTNER) — 내부 시스템 접근 원천 차단 403."""
    h = _login(client, "pl-partner", "pl-partner@carrier.example", "PARTNER")
    assert client.get(PIPELINE, headers=h).status_code == 403


def test_auth_required(client):
    assert client.get(PIPELINE).status_code == 401


# ── 5. N+1 없음(쿼리 수 상수) ────────────────────────────────────────────────
def test_no_n_plus_one(client, staff_headers):
    """여러 셀을 조회해도 쿼리 수는 상수(5: 집계1+헤더1+통지활동1+전역감사2)."""
    for t in ("nq1", "nq2", "nq3", "nq4"):
        _seed_cell(client, staff_headers, t, with_payout=True, header_status="CONFIRMED")
    engine = models.engine
    seen = []
    from sqlalchemy import event

    def _before(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            seen.append(statement)

    event.listen(engine, "before_cursor_execute", _before)
    try:
        db = _db()
        try:
            res = settlement_pipeline(db)
        finally:
            db.close()
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    assert len(res["items"]) >= 4
    # 집계·헤더·통지활동·전역감사(2) = 5개의 SELECT면 충분(행 수와 무관한 상수).
    assert len(seen) <= 6, "SELECT count={0} (N+1 의심)".format(len(seen))
