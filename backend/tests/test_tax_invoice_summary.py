"""세금계산서 요약(GET /tax-invoices/summary) — 매입·매출·순액·부가세 + 월별 추이."""

from datetime import date

import models

API = "/api/v1/tax-invoices/summary"


def _login(client, email):
    r = client.post("/api/v1/auth/dev-login", json={"email": email})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer {0}".format(r.json()["access_token"])}


def _mk(db, approval, direction, supply, tax, y, m, d):
    db.add(models.TaxInvoice(
        approval_no=approval, direction=direction,
        supply_amount=supply, tax_amount=tax, total_amount=supply + tax,
        issue_date=date(y, m, d), source="HTML_IMPORT",
    ))


def test_summary_totals_net_and_monthly(client):
    db = models.SessionLocal()
    try:
        db.query(models.TaxInvoice).filter(
            models.TaxInvoice.approval_no.like("TESTSUM%")
        ).delete(synchronize_session=False)
        _mk(db, "TESTSUM01", "매출", 3_000_000, 300_000, 2026, 7, 5)
        _mk(db, "TESTSUM02", "매출", 2_000_000, 200_000, 2026, 8, 10)
        _mk(db, "TESTSUM03", "매입", 1_000_000, 100_000, 2026, 7, 20)
        _mk(db, "TESTSUM04", "매입", 500_000, 50_000, 2026, 8, 2)
        db.commit()
    finally:
        db.close()

    headers = _login(client, "manager@hooxipartners.com")
    r = client.get(API, headers=headers, params={"date_from": "2026-07-01", "date_to": "2026-08-31"})
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["sales_supply"] == 5_000_000
    assert s["purchase_supply"] == 1_500_000
    assert s["net_supply"] == 3_500_000
    assert s["sales_tax"] == 500_000
    assert s["purchase_tax"] == 150_000
    assert s["sales_count"] == 2 and s["purchase_count"] == 2
    months = {m["month"]: m for m in s["months"]}
    assert months["2026-07"]["sales"] == 3_000_000
    assert months["2026-07"]["net"] == 2_000_000  # 3.0M 매출 - 1.0M 매입
    assert months["2026-08"]["net"] == 1_500_000  # 2.0M - 0.5M

    # 기간 필터 — 7월만
    r2 = client.get(API, headers=headers, params={"date_from": "2026-07-01", "date_to": "2026-07-31"})
    s2 = r2.json()
    assert s2["sales_supply"] == 3_000_000 and s2["purchase_supply"] == 1_000_000

    db = models.SessionLocal()
    try:
        db.query(models.TaxInvoice).filter(
            models.TaxInvoice.approval_no.like("TESTSUM%")
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_summary_requires_auth(client):
    assert client.get(API).status_code == 401
