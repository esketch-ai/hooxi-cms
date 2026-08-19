"""예상수익(B2) 4엔드포인트 정합 — 시세×잔여반영감축량 파생값이 grain별로 일관되는지.

검증 대상 4곳: 사업상세(GET /projects/{id})·자산관리보고(settlement-summary)·자산차량목록
(asset-vehicles)·재무원장(finance-ledger). 산식은 services.market_rate.expected_revenue
(leaf에서 Σeff×6개월평균시세 원단위 절사)로 통일 — 정합은 'leaf-TRUNC 후 파이썬 합산'이라
원단위까지 정확히 성립해야 한다.

시세 테이블은 세션 공유 SQLite를 누수 없이 쓰기 위해 module autouse 픽스처로
원본 스냅샷→비움→복원한다(참고: tests/test_market_rate_trailing.py). 각 테스트는
필요한 시세만 직접 심고, 예상수익 leaf 파생을 위해 payout-params까지 설정한 사업/차량을
고유 접두어로 구성해 finance-ledger 검색으로 자기 사업만 좁혀 총계 정합을 본다.
"""

from datetime import date

import pytest

import models

API = "/api/v1"
PROJECTS = API + "/projects"
SUMMARY = API + "/asset-report/settlement-summary"
LEDGER = API + "/finance-ledger"
VEHICLES = API + "/asset-vehicles"

# 이 모듈이 만드는 사업의 고유 접두어 — finance-ledger 검색으로 자기 사업만 좁힌다.
TAG = "예수정합XR"


# ── 시세 격리(module autouse) — 원본 스냅샷→비움→복원(공유 SQLite 누수 방지) ──────
@pytest.fixture(autouse=True)
def _isolate_market_rates(client):
    db = models.SessionLocal()
    try:
        saved = [
            {c.name: getattr(r, c.name) for c in models.MarketRate.__table__.columns}
            for r in db.query(models.MarketRate).all()
        ]
        db.query(models.MarketRate).delete()
        db.commit()
    finally:
        db.close()
    yield
    db = models.SessionLocal()
    try:
        db.query(models.MarketRate).delete()
        for row in saved:
            db.add(models.MarketRate(**row))
        db.commit()
    finally:
        db.close()


def _reset_rates(db):
    db.query(models.MarketRate).delete()
    db.commit()


def _set_rate(price):
    """시세 1건 심기 — 충분히 이른 effective_date라 직전 6개월 월말이 모두 이 단가로 해석된다.

    (오늘 의존 회피 — as_of가 언제든 직전 6개월 월말이 이 단가 하나로 평균되어 avg6=price)
    """
    db = models.SessionLocal()
    try:
        _reset_rates(db)
        db.add(models.MarketRate(effective_date=date(2000, 1, 1), unit_price=price))
        db.commit()
    finally:
        db.close()


def _clear_rate():
    db = models.SessionLocal()
    try:
        _reset_rates(db)
    finally:
        db.close()


# ── 시드 헬퍼(test_settlement_summary 관용구 재사용) ─────────────────────────────
def _mk_client(client, headers, tag):
    r = client.post(API + "/clients", headers=headers,
                    json={"client_type": "TRANSPORT", "company_name": TAG + tag})
    assert r.status_code == 201, r.text
    return r.json()["client_id"]


def _capped_vehicle(per_year, cid):
    p = {"registered_at": "2016-01-01", "client_id": cid}
    for i in range(1, 9):
        p["reduction_y{0}".format(i)] = per_year
    return p


def _mk_project(client, headers, name):
    r = client.post(PROJECTS, headers=headers,
                    json={"project_name": name, "project_status": "기획"})
    assert r.status_code == 201, r.text
    return r.json()["project_id"]


def _add_vehicle(client, headers, pid, per_year, cid):
    r = client.post(f"{PROJECTS}/{pid}/vehicles", headers=headers,
                    json=_capped_vehicle(per_year, cid))
    assert r.status_code == 201, r.text


def _set_payout(client, headers, pid):
    # payout-params 설정 → effective_reduction·expected_payout 파생 채워짐(예상수익 leaf 조달)
    r = client.put(f"{PROJECTS}/{pid}/payout-params", headers=headers,
                   json={"max_payment": 1200000, "approved_at": "2016-02-01"})
    assert r.status_code == 200, r.text


@pytest.fixture(scope="module")
def seed(client, manager_headers):
    """단일 운수사 c1 + 2사업(pA:2대, pB:1대) + payout 설정. 사업명은 고유 접두어로 검색 격리."""
    c1 = _mk_client(client, manager_headers, "C1")
    pa = _mk_project(client, manager_headers, TAG + "사업A")
    pb = _mk_project(client, manager_headers, TAG + "사업B")
    _add_vehicle(client, manager_headers, pa, 30, c1)
    _add_vehicle(client, manager_headers, pa, 30, c1)
    _add_vehicle(client, manager_headers, pb, 20, c1)
    _set_payout(client, manager_headers, pa)
    _set_payout(client, manager_headers, pb)
    return {"client_id": c1, "pa": pa, "pb": pb}


def _ledger_rows(client, headers):
    """finance-ledger를 이 모듈 사업만으로 좁혀(검색) 사업행 목록 반환(전건 노출 page_size)."""
    r = client.get(LEDGER, headers=headers,
                   params={"search": TAG, "page_size": 200})
    assert r.status_code == 200, r.text
    return r.json()


# ── 1) 4곳 모두 예상수익·6개월평균시세가 실리고, 시세 있으면 양수 ────────────────
def test_all_four_expose_expected_revenue_positive(client, manager_headers, seed):
    _set_rate(1000)

    # 사업상세
    d = client.get(f"{PROJECTS}/{seed['pa']}", headers=manager_headers).json()
    assert d["market_rate_avg6"] == 1000.0
    assert d["expected_revenue"] is not None and d["expected_revenue"] > 0

    # 자산관리보고(settlement-summary) — 셀 leaf
    s = client.get(SUMMARY, headers=manager_headers,
                   params={"client_id": seed["client_id"]}).json()
    assert s["market_rate_avg6"] == 1000.0
    row = s["items"][0]
    assert row["expected_revenue"] is not None and row["expected_revenue"] > 0
    for p in row["projects"]:
        assert p["expected_revenue"] is not None and p["expected_revenue"] > 0

    # 자산차량목록(asset-vehicles) — 차량 leaf
    v = client.get(VEHICLES, headers=manager_headers,
                   params={"project_id": seed["pa"]}).json()
    assert v["market_rate_avg6"] == 1000.0
    assert len(v["items"]) == 2
    for it in v["items"]:
        assert it["expected_revenue"] is not None and it["expected_revenue"] > 0

    # 재무원장(finance-ledger) — 사업행 leaf
    fl = _ledger_rows(client, manager_headers)
    assert fl["market_rate_avg6"] == 1000.0
    for it in fl["items"]:
        assert it["expected_revenue"] is not None and it["expected_revenue"] > 0


# ── 2) 자산관리보고 정합 — Σ셀 == 운수사행 == totals(원단위까지 정확) ────────────
def test_asset_report_rollup_reconciles_exact(client, manager_headers, seed):
    _set_rate(1000)
    s = client.get(SUMMARY, headers=manager_headers,
                   params={"client_id": seed["client_id"]}).json()
    assert s["total"] == 1  # client_id 필터 → 단일 운수사행
    row = s["items"][0]
    # Σ셀 예상수익 == 운수사행 예상수익(leaf-TRUNC 후 합산, 원단위 일치)
    cell_sum = sum(p["expected_revenue"] for p in row["projects"])
    assert cell_sum == row["expected_revenue"]
    # 운수사행(단일) == 전사 총계
    assert row["expected_revenue"] == s["totals"]["expected_revenue"]


# ── 3) 재무원장 정합 — Σ사업행 == totals.expected_revenue(원단위까지 정확) ────────
def test_finance_ledger_rollup_reconciles_exact(client, manager_headers, seed):
    _set_rate(1000)
    fl = _ledger_rows(client, manager_headers)
    row_sum = sum(it["expected_revenue"] for it in fl["items"])
    assert row_sum == fl["totals"]["expected_revenue"]


# ── 4) 교차 일치 — 동일 사업의 사업상세 == 재무원장 사업행(원단위까지) ────────────
def test_cross_match_detail_equals_ledger_row(client, manager_headers, seed):
    _set_rate(1000)
    d = client.get(f"{PROJECTS}/{seed['pa']}", headers=manager_headers).json()
    fl = _ledger_rows(client, manager_headers)
    ledger_by_pid = {it["project_id"]: it for it in fl["items"]}
    assert seed["pa"] in ledger_by_pid
    assert d["expected_revenue"] == ledger_by_pid[seed["pa"]]["expected_revenue"]


# ── 5) 시세 전무 — 4곳 모두 예상수익·6개월평균시세가 None ─────────────────────────
def test_no_market_rate_yields_none_everywhere(client, manager_headers, seed):
    _clear_rate()

    d = client.get(f"{PROJECTS}/{seed['pa']}", headers=manager_headers).json()
    assert d["market_rate_avg6"] is None
    assert d["expected_revenue"] is None

    s = client.get(SUMMARY, headers=manager_headers,
                   params={"client_id": seed["client_id"]}).json()
    assert s["market_rate_avg6"] is None
    row = s["items"][0]
    assert row["expected_revenue"] is None
    for p in row["projects"]:
        assert p["expected_revenue"] is None

    v = client.get(VEHICLES, headers=manager_headers,
                   params={"project_id": seed["pa"]}).json()
    assert v["market_rate_avg6"] is None
    for it in v["items"]:
        assert it["expected_revenue"] is None

    fl = _ledger_rows(client, manager_headers)
    assert fl["market_rate_avg6"] is None
    for it in fl["items"]:
        assert it["expected_revenue"] is None


# ── 6) 전건 NULL(지급파라미터 미설정) — 사업상세 예상수익이 0이 아니라 None (MED 회귀가드) ──
#    coalesce(eff,0)을 쓰면 사업상세만 '0원'이 되어 raw SUM(None)인 재무원장·자산차량과 발산한다.
#    (이 테스트는 파일 정의 순서상 마지막 — 위 정합 테스트들에 지급 미설정 사업이 섞이지 않는다.)
def test_all_null_effective_reduction_detail_is_none_not_zero(client, manager_headers, seed):
    _set_rate(1000)
    # payout-params 미설정 사업 + 차량 → effective_reduction 전건 NULL
    p_null = _mk_project(client, manager_headers, TAG + "무지급")
    _add_vehicle(client, manager_headers, p_null, 30, seed["client_id"])

    d = client.get(f"{PROJECTS}/{p_null}", headers=manager_headers).json()
    assert d["market_rate_avg6"] == 1000.0  # 시세는 존재
    assert d["expected_revenue"] is None  # 그럼에도 Σeff=None → None (0원 아님)

    # 재무원장에 이 사업행이 나타나면 예상수익도 None으로 교차 일치(0원 vs '-' 발산 없음)
    fl = _ledger_rows(client, manager_headers)
    lb = {it["project_id"]: it for it in fl["items"]}
    if p_null in lb:
        assert lb[p_null]["expected_revenue"] is None
        assert d["expected_revenue"] == lb[p_null]["expected_revenue"]
