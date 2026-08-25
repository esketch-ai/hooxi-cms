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


def test_issue_counts_and_filter(client):
    db = models.SessionLocal()
    try:
        db.query(models.TaxInvoice).filter(
            models.TaxInvoice.approval_no.like("TESTISS%")
        ).delete(synchronize_session=False)
        # 미연결·미매칭 (project/client/buyer 모두 없음)
        db.add(models.TaxInvoice(approval_no="TESTISS01", direction="매출",
                                 supply_amount=1_000_000, tax_amount=100_000, total_amount=1_100_000,
                                 issue_date=date(2026, 8, 1), source="HTML_IMPORT"))
        # 음수(수정취소)
        db.add(models.TaxInvoice(approval_no="TESTISS02", direction="매출",
                                 supply_amount=-500_000, tax_amount=-50_000, total_amount=-550_000,
                                 issue_date=date(2026, 8, 2), source="HTML_IMPORT"))
        db.commit()
    finally:
        db.close()

    headers = _login(client, "manager@hooxipartners.com")
    c = client.get("/api/v1/tax-invoices/issue-counts", headers=headers).json()
    assert c["unlinked"] >= 2      # 둘 다 project 미연결
    assert c["unmatched"] >= 2     # 둘 다 상대 미매칭
    assert c["negative"] >= 1      # 음수 1건

    # 필터 목록 — negative
    neg = client.get("/api/v1/tax-invoices", headers=headers, params={"issue": "negative"}).json()
    assert any(i["approval_no"] == "TESTISS02" for i in neg["items"])
    assert all((i["supply_amount"] or 0) < 0 for i in neg["items"] if i["approval_no"].startswith("TESTISS"))

    db = models.SessionLocal()
    try:
        db.query(models.TaxInvoice).filter(
            models.TaxInvoice.approval_no.like("TESTISS%")
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_breakdown_axes_and_export(client):
    db = models.SessionLocal()
    try:
        db.query(models.TaxInvoice).filter(
            models.TaxInvoice.approval_no.like("TESTBRK%")
        ).delete(synchronize_session=False)
        db.add(models.TaxInvoice(
            approval_no="TESTBRK01", direction="매출", supply_amount=2_000_000,
            tax_amount=200_000, total_amount=2_200_000, issue_date=date(2026, 8, 1),
            invoicer_reg_no="1000000001", invoicer_name="후시파트너스",
            counterpart_reg_no="2000000002", counterpart_name="가나운수", source="HTML_IMPORT",
        ))
        db.add(models.TaxInvoice(
            approval_no="TESTBRK02", direction="매입", supply_amount=800_000,
            tax_amount=80_000, total_amount=880_000, issue_date=date(2026, 8, 5),
            invoicee_reg_no="1000000001", invoicee_name="후시파트너스",
            counterpart_reg_no="2000000002", counterpart_name="가나운수", source="HTML_IMPORT",
        ))
        db.commit()
    finally:
        db.close()

    headers = _login(client, "manager@hooxipartners.com")
    # 거래처별 — 가나운수: 매출 2.0M / 매입 0.8M / 순액 1.2M
    b = client.get("/api/v1/tax-invoices/breakdown", headers=headers,
                   params={"axis": "counterpart", "date_from": "2026-08-01", "date_to": "2026-08-31"}).json()
    row = next(r for r in b["rows"] if r["label"] == "가나운수")
    assert row["sales"] == 2_000_000 and row["purchase"] == 800_000 and row["net"] == 1_200_000
    # 자사법인별 — 후시파트너스로 묶임
    e = client.get("/api/v1/tax-invoices/breakdown", headers=headers,
                   params={"axis": "entity", "date_from": "2026-08-01", "date_to": "2026-08-31"}).json()
    assert any(r["label"] == "후시파트너스" for r in e["rows"])
    # 잘못된 축 422
    assert client.get("/api/v1/tax-invoices/breakdown", headers=headers, params={"axis": "bad"}).status_code == 422
    # 엑셀 내보내기 200 + xlsx
    ex = client.get("/api/v1/tax-invoices/export", headers=headers,
                    params={"date_from": "2026-08-01", "date_to": "2026-08-31"})
    assert ex.status_code == 200
    assert "spreadsheet" in ex.headers.get("content-type", "")

    db = models.SessionLocal()
    try:
        db.query(models.TaxInvoice).filter(
            models.TaxInvoice.approval_no.like("TESTBRK%")
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()
