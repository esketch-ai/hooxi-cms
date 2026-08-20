"""세금계산서 원장 API (P5) — preview/commit/list 라우터 + 멱등."""

import models
from test_tax_invoice_import import (  # 합성 보안메일 빌더 재사용
    COMPANY,
    COUNTERPART,
    SAMPLE_XML,
    _build_secure_mail,
)

API = "/api/v1/tax-invoices"


def _file(html: str):
    return ("files", ("t.html", html.encode("utf-8"), "text/html"))


def _cleanup(db, cid):
    db.query(models.TaxInvoice).filter(
        models.TaxInvoice.approval_no.like("TESTIMP%")
    ).delete(synchronize_session=False)
    if cid:
        db.query(models.Client).filter(models.Client.client_id == cid).delete(
            synchronize_session=False
        )
    row = db.get(models.Config, "company_biz_reg_no")
    if row:
        row.config_value = ""
    db.commit()


def test_tax_invoice_api_preview_commit_list_idempotent(client, staff_headers):
    db = models.SessionLocal()
    cid = None
    try:
        _cleanup(db, None)
        db.merge(models.Config(config_key="company_biz_reg_no", config_value=COMPANY))
        c = models.Client(client_type="TRANSPORT", company_name="테스트API운수", biz_reg_no=COUNTERPART)
        db.add(c)
        db.commit()
        cid = c.client_id

        html = _build_secure_mail(SAMPLE_XML, COMPANY)

        # 미리보기
        r = client.post(API + "/preview", headers=staff_headers, files=[_file(html)])
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert len(items) == 1
        it = items[0]
        assert it["ok"] and it["direction"] == "매입"
        assert it["matched_client_id"] == cid
        assert it["supply_amount"] == 16200000
        assert it["is_duplicate"] is False

        # 적용
        r = client.post(API + "/commit", headers=staff_headers, files=[_file(html)])
        assert r.status_code == 200, r.text
        assert r.json()["created"] == 1

        # 조회
        r = client.get(API, headers=staff_headers, params={"search": COUNTERPART})
        assert r.status_code == 200
        assert r.json()["total"] >= 1
        assert any(row["direction"] == "매입" for row in r.json()["items"])

        # 재적용 → 멱등(중복)
        r = client.post(API + "/commit", headers=staff_headers, files=[_file(html)])
        assert r.json()["duplicate"] == 1
        assert r.json()["created"] == 0
    finally:
        _cleanup(db, cid)
        db.close()


def test_tax_invoice_preview_requires_auth(client):
    r = client.post(API + "/preview", files=[_file("<html></html>")])
    assert r.status_code in (401, 403)
