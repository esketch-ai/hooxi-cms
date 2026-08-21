"""경영 관찰 OB-R1 — summary(KPI·추이·퍼널)·detail(개요+담당자)·OBSERVER 접근."""

from datetime import date, datetime

import models
from auth import create_access_token
from routers import common


def _cleanup(db):
    for model, col, pat in [
        (models.TaxInvoice, models.TaxInvoice.counterpart_name, "TESTOB%"),
        (models.Settlement, None, None),
        (models.MarketRate, models.MarketRate.note, "TESTOB%"),
        (models.FleetStatus, models.FleetStatus.company_name, "TESTOB%"),
    ]:
        pass
    db.query(models.TaxInvoice).filter(
        models.TaxInvoice.counterpart_name.like("TESTOB%")).delete(synchronize_session=False)
    db.query(models.Settlement).filter(models.Settlement.project_id.in_(
        db.query(models.Project.project_id).filter(models.Project.project_name.like("TESTOB%"))
    )).delete(synchronize_session=False)
    db.query(models.ProjectVehicle).filter(models.ProjectVehicle.project_id.in_(
        db.query(models.Project.project_id).filter(models.Project.project_name.like("TESTOB%"))
    )).delete(synchronize_session=False)
    db.query(models.MarketRate).filter(
        models.MarketRate.note.like("TESTOB%")).delete(synchronize_session=False)
    db.query(models.FleetStatus).filter(
        models.FleetStatus.company_name.like("TESTOB%")).delete(synchronize_session=False)
    db.query(models.Project).filter(
        models.Project.project_name.like("TESTOB%")).delete(synchronize_session=False)
    db.query(models.Client).filter(
        models.Client.company_name.like("TESTOB%")).delete(synchronize_session=False)
    db.commit()


def _seed(db):
    now = common.now_kst()
    cur = "{0:04d}-{1:02d}".format(now.year, now.month)
    c = models.Client(client_type="TRANSPORT", company_name="TESTOB운수",
                      region="서울", contract_status="ACTIVE")
    db.add(c); db.commit()
    p = models.Project(project_name="TESTOB사업", project_status="추진")
    db.add(p); db.commit()
    db.add_all([
        # 이번 달 매출 2건·매입 1건
        models.TaxInvoice(direction="매출", issue_date=now.date(), supply_amount=1000000,
                          counterpart_name="TESTOB증권", project_id=p.project_id),
        models.TaxInvoice(direction="매출", issue_date=now.date(), supply_amount=500000,
                          counterpart_name="TESTOB금융"),
        models.TaxInvoice(direction="매입", issue_date=now.date(), supply_amount=300000,
                          counterpart_name="TESTOB운수"),
        # 정산: 청구 1(미수) + 완료 1(이번 달 입금)
        models.Settlement(client_id=c.client_id, project_id=p.project_id, period="2026-05",
                          status="BILLED", confirmed_amount=800000,
                          billed_at=now, confirmed_at=now),
        models.Settlement(client_id=c.client_id, project_id=p.project_id, period="2026-06",
                          status="COMPLETED", confirmed_amount=700000, paid_amount=700000,
                          confirmed_at=now, billed_at=now, completed_at=now),
        models.MarketRate(effective_date=date(2026, 1, 1), unit_price=10000, note="TESTOB1"),
        models.MarketRate(effective_date=date(2026, 6, 1), unit_price=12000, note="TESTOB2"),
        models.FleetStatus(client_id=c.client_id, region="서울", industry="CITY",
                           company_name="TESTOB운수", period=cur,
                           license_count=100, total_count=100, electric=40),
    ])
    db.commit()
    return c.client_id, p.project_id, cur


def test_summary_shapes_and_numbers(client, admin_headers):
    db = models.SessionLocal()
    try:
        _cleanup(db)
        cid, pid, cur = _seed(db)
    finally:
        db.close()
    r = client.get("/api/v1/observe/summary?months=12", headers=admin_headers)
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d["months"]) == 12 and d["months"][-1] == cur
    row = [x for x in d["finance_trend"] if x["month"] == cur][0]
    assert row["revenue"] >= 1500000 and row["purchase"] >= 300000
    assert row["paid"] >= 700000
    # KPI — 매출/이익/미수
    assert d["kpi"]["revenue"]["value"] >= 1500000
    assert d["kpi"]["receivable"]["value"] >= 800000 and d["kpi"]["receivable"]["count"] >= 1
    # 퍼널 4단계 존재 + 청구 단계 집계
    keys = [f["key"] for f in d["funnel"]]
    assert keys == ["SCHEDULED", "CONFIRMED", "BILLED", "COMPLETED"]
    billed = [f for f in d["funnel"] if f["key"] == "BILLED"][0]
    assert billed["count"] >= 1 and billed["amount"] >= 800000
    # 시세·전기 전환
    assert len(d["market_rates"]) >= 2
    ev = [x for x in d["ev_trend"] if x["month"] == cur]
    assert ev and ev[0]["ev_share"] >= 40.0
    # 잘못된 months → 422
    assert client.get("/api/v1/observe/summary?months=7", headers=admin_headers).status_code == 422
    db = models.SessionLocal()
    try:
        _cleanup(db)
    finally:
        db.close()


def test_detail_topics_with_manager(client, admin_headers):
    db = models.SessionLocal()
    try:
        _cleanup(db)
        cid, pid, cur = _seed(db)
        # 담당자 연결 — 고객사 담당(매니저)
        mgr = db.query(models.User).filter(models.User.role == "MANAGER").first()
        cli = db.get(models.Client, cid)
        cli.manager_id = mgr.user_id
        db.commit()
        mgr_name = mgr.name or mgr.email
    finally:
        db.close()
    # 미수(개요) — 담당자 이름 포함·경과일 정렬
    r = client.get("/api/v1/observe/detail?topic=receivable", headers=admin_headers)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["items"] and d["items"][0]["manager"] == mgr_name
    assert d["items"][0]["client_name"].startswith("TESTOB")
    assert "청구" in d["explain"]
    # 월 개요 — 매출 상위·해설
    r2 = client.get(f"/api/v1/observe/detail?topic=month&key={cur}", headers=admin_headers)
    d2 = r2.json()
    assert d2["sales_total"] >= 1500000
    assert d2["sales_top"][0]["counterpart"].startswith("TESTOB")
    # 퍼널 단계 개요
    r3 = client.get("/api/v1/observe/detail?topic=funnel&key=BILLED", headers=admin_headers)
    assert r3.json()["items"][0]["amount"] >= 800000
    # 시세 개요
    r4 = client.get("/api/v1/observe/detail?topic=rate", headers=admin_headers)
    assert len(r4.json()["items"]) >= 2
    # 미지원 topic → 422
    assert client.get("/api/v1/observe/detail?topic=nope", headers=admin_headers).status_code == 422
    db = models.SessionLocal()
    try:
        _cleanup(db)
    finally:
        db.close()


def test_observer_can_access_observe_api(client):
    db = models.SessionLocal()
    try:
        u = db.get(models.User, "t-ob-observer")
        if u is None:
            u = models.User(user_id="t-ob-observer", email="t-ob@hooxi.kr",
                            role="OBSERVER", status="ACTIVE")
            db.add(u); db.commit()
        db.refresh(u); db.expunge(u)
    finally:
        db.close()
    h = {"Authorization": "Bearer " + create_access_token(u)}
    assert client.get("/api/v1/observe/summary?months=12", headers=h).status_code == 200
    assert client.get("/api/v1/observe/detail?topic=rate", headers=h).status_code == 200
    # 화이트리스트 밖은 여전히 403(격리 회귀 없음)
    assert client.get("/api/v1/settlements", headers=h).status_code == 403
    db = models.SessionLocal()
    try:
        db.query(models.User).filter_by(user_id="t-ob-observer").delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()
