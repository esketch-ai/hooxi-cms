"""포털 전용 뷰 스키마·빌더 (Phase 4 INC-4 / 부록 N.3 기밀 매트릭스).

핵심: 금지 필드를 스키마에 아예 선언하지 않아 서버가 원천 미포함(마스킹 아님).
어느 뷰도 원가와 매출을 동시에 담지 않는다(H.6). 엔드포인트는 INC-5 — 여기서는
스키마 금지필드 부재(정적) + 빌더 동작 + 역산 차단만 검증한다.
"""

import models
import schemas
from services.portal import build_investor_view, build_partner_view

API = "/api/v1"
PROJECTS = API + "/projects"


def _mk_project(client, headers, name):
    r = client.post(PROJECTS, headers=headers, json={"project_name": name, "project_status": "기획"})
    assert r.status_code == 201, r.text
    return r.json()["project_id"]


def _mk_client(client, headers, name):
    r = client.post(API + "/clients", headers=headers, json={"client_type": "TRANSPORT", "company_name": name})
    assert r.status_code == 201, r.text
    return r.json()["client_id"]


def _capped_vehicle(client_id, per_year):
    """잔여차령 8 캡 노후차 — y1..y8 동일값(잔여반영=Σ). 등록 2016-01-01, 운수사 지정."""
    p = {"registered_at": "2016-01-01", "client_id": client_id}
    for i in range(1, 9):
        p[f"reduction_y{i}"] = per_year
    return p


# ── 1. 스키마 금지필드 부재(정적) ──────────────────────────────────────────
def test_partner_view_forbidden_fields_absent():
    keys = set(schemas.PartnerPortalView.model_fields)
    forbidden = {"sale", "sale_amount", "sale_unit_price", "margin", "margin_amount",
                 "margin_ratio", "payout_rate", "product", "sale_recognized", "gross_profit",
                 "total_contract_revenue", "my_contract"}
    assert forbidden.isdisjoint(keys), forbidden & keys


def test_investor_view_forbidden_fields_absent():
    keys = set(schemas.InvestorPortalView.model_fields)
    forbidden = {"payout", "payout_amount", "expected_payment", "expected_payout",
                 "product", "payout_rate", "sale_recognized", "gross_profit", "margin",
                 "margin_amount", "wip", "wip1", "wip2", "inventory", "my_expected_payout"}
    assert forbidden.isdisjoint(keys), forbidden & keys


# ── 2. 빌더 동작 ─────────────────────────────────────────────────────────────
def test_partner_view_self_only(client, staff_headers):
    """차량 2운수사 + payout-params → 파트너 뷰가 자기(A) 감축량·수혜금액만, B 미포함."""
    pid = _mk_project(client, staff_headers, "포털파트너검증")
    ca = _mk_client(client, staff_headers, "운수사갑")
    cb = _mk_client(client, staff_headers, "운수사을")
    # A: capped(30)=payout 1,200,000 / capped(15)=600,000 → A Σ payout 1,800,000, eff 360
    client.post(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers, json=_capped_vehicle(ca, 30))
    client.post(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers, json=_capped_vehicle(ca, 15))
    # B: capped(10)=payout 400,000, eff 80
    client.post(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers, json=_capped_vehicle(cb, 10))
    client.put(
        f"{PROJECTS}/{pid}/payout-params",
        headers=staff_headers,
        json={"max_payment": 1200000, "approved_at": "2016-02-01"},
    )

    db = models.SessionLocal()
    try:
        project = db.query(models.Project).filter(models.Project.project_id == pid).first()
        view = build_partner_view(db, project, ca)
    finally:
        db.close()

    assert view.my_vehicle_count == 2  # A 차량만(B의 1대 미포함)
    assert view.my_effective_reduction == 360  # 240 + 120 (B 80 미포함)
    assert view.my_expected_payout == 1800000  # 1,200,000 + 600,000 (B 미포함)


def test_investor_view_anonymous_and_revenue(client, staff_headers):
    """투자 뷰 — 운수사별 감축량(익명 라벨)·총매출, 예상지급액/원가 키 없음."""
    pid = _mk_project(client, staff_headers, "포털투자검증")
    ca = _mk_client(client, staff_headers, "투자운수사갑")
    cb = _mk_client(client, staff_headers, "투자운수사을")
    client.post(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers, json=_capped_vehicle(ca, 30))
    client.post(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers, json=_capped_vehicle(ca, 15))
    client.post(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers, json=_capped_vehicle(cb, 10))
    client.put(
        f"{PROJECTS}/{pid}/payout-params",
        headers=staff_headers,
        json={"max_payment": 1200000, "approved_at": "2016-02-01"},
    )
    # 매수자 마스터 + 자기 계약(실발행 3,000,000)
    bid = client.post(
        API + "/buyers", headers=staff_headers, json={"name": "투자사알파", "buyer_type": "투자사"}
    ).json()["buyer_id"]
    client.post(
        f"{PROJECTS}/{pid}/sales",
        headers=staff_headers,
        json={"buyer_name": "투자사알파", "buyer_id": bid, "sale_invoice_amount": 3000000,
              "sale_unit_price": 15000, "quantity": 200, "ownership_pct": 100},
    )

    db = models.SessionLocal()
    try:
        project = db.query(models.Project).filter(models.Project.project_id == pid).first()
        view = build_investor_view(db, project, bid)
    finally:
        db.close()

    # 익명 라벨(감축량 내림차순): 운수사 1 = A(360, 2대), 운수사 2 = B(80, 1대)
    ops = view.operators_reduction
    assert [o["label"] for o in ops] == ["운수사 1", "운수사 2"]
    assert ops[0]["vehicle_count"] == 2 and ops[0]["effective_reduction"] == 360
    assert ops[1]["vehicle_count"] == 1 and ops[1]["effective_reduction"] == 80
    # 라벨은 익명 — client 이름 노출 없음
    joined = " ".join(o["label"] for o in ops)
    assert "갑" not in joined and "을" not in joined
    assert view.total_effective_reduction == 440  # 360 + 80
    assert view.total_contract_revenue == 3000000  # 실발행액 gross
    # 자기 계약(본인 것만) — 매출 축
    assert view.my_contract["gross_revenue"] == 3000000
    assert view.my_contract["sale_invoice_amount"] == 3000000

    # 예상지급액 키 부재(스키마에 미선언)
    assert "my_expected_payout" not in view.model_dump()
    assert "expected_payment" not in view.model_dump()


# ── 3. 역산 차단 ─────────────────────────────────────────────────────────────
def test_investor_view_no_cost_keys(client, staff_headers):
    """투자 뷰 dict에 원가·지급률·매출인식 키가 하나도 없음(원가+매출 동시 부재)."""
    pid = _mk_project(client, staff_headers, "포털역산차단검증")
    ca = _mk_client(client, staff_headers, "역산운수사갑")
    client.post(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers, json=_capped_vehicle(ca, 30))
    client.put(
        f"{PROJECTS}/{pid}/payout-params",
        headers=staff_headers,
        json={"max_payment": 1200000, "approved_at": "2016-02-01"},
    )
    bid = client.post(
        API + "/buyers", headers=staff_headers, json={"name": "역산투자사", "buyer_type": "투자사"}
    ).json()["buyer_id"]
    client.post(
        f"{PROJECTS}/{pid}/sales",
        headers=staff_headers,
        json={"buyer_name": "역산투자사", "buyer_id": bid, "sale_invoice_amount": 3000000, "ownership_pct": 100},
    )

    db = models.SessionLocal()
    try:
        project = db.query(models.Project).filter(models.Project.project_id == pid).first()
        dumped = build_investor_view(db, project, bid).model_dump()
    finally:
        db.close()

    # 최상위 키 + my_contract 하위 키 전체를 훑어 원가·회계 키 부재 확인
    all_keys = set(dumped)
    if isinstance(dumped.get("my_contract"), dict):
        all_keys |= set(dumped["my_contract"])
    cost_keys = {"payout", "payout_amount", "expected_payment", "expected_payout",
                 "payout_rate", "product", "sale_recognized", "gross_profit", "wip1",
                 "wip2", "liability", "inventory", "margin_amount", "margin_ratio"}
    assert cost_keys.isdisjoint(all_keys), cost_keys & all_keys
