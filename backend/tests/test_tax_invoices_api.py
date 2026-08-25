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


def test_tax_invoice_scan_dropbox(client, staff_headers, monkeypatch):
    import services.dropbox_storage as ds

    html = _build_secure_mail(SAMPLE_XML, COMPANY)
    monkeypatch.setattr(ds, "is_configured", lambda: True)
    monkeypatch.setattr(ds, "root", lambda: "")
    monkeypatch.setattr(
        ds, "list_folder",
        lambda p: [{"name": "t.html", "path_display": "/정산/t.html", "is_dir": False}],
    )
    monkeypatch.setattr(ds, "download", lambda p: html.encode("utf-8"))

    db = models.SessionLocal()
    cid = None
    try:
        _cleanup(db, None)
        db.merge(models.Config(config_key="company_biz_reg_no", config_value=COMPANY))
        c = models.Client(client_type="TRANSPORT", company_name="스캔운수", biz_reg_no=COUNTERPART)
        db.add(c)
        db.commit()
        cid = c.client_id

        r = client.post(API + "/scan/preview", headers=staff_headers, params={"folder": "/정산"})
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert len(items) == 1 and items[0]["ok"] and items[0]["direction"] == "매입"

        r = client.post(API + "/scan/commit", headers=staff_headers, params={"folder": "/정산"})
        assert r.status_code == 200, r.text
        assert r.json()["created"] == 1
    finally:
        _cleanup(db, cid)
        db.close()


def test_rematch_backfill_links_late_client(client, staff_headers):
    """미매칭으로 굳은 세금계산서가, 나중에 고객사 등록 후 재매칭 백필로 자동 연결."""
    db = models.SessionLocal()
    cid = None
    try:
        _cleanup(db, None)
        db.merge(models.Config(config_key="company_biz_reg_no", config_value=COMPANY))
        db.commit()  # 자사만 등록 — 상대(COUNTERPART) 고객사는 아직 없음
        # 적재 → 상대 미등록이라 미매칭으로 굳음
        html = _build_secure_mail(SAMPLE_XML, COMPANY)
        r = client.post(API + "/commit", headers=staff_headers, files=[_file(html)])
        assert r.status_code == 200, r.text
        assert r.json()["created"] == 1
        inv = db.query(models.TaxInvoice).filter(
            models.TaxInvoice.approval_no.like("TESTIMP%")).first()
        assert inv.matched_client_id is None and inv.matched_buyer_id is None  # 미매칭

        # 재업로드해도 멱등(중복)이라 재매칭 안 됨 확인
        r2 = client.post(API + "/commit", headers=staff_headers, files=[_file(html)])
        assert r2.json()["duplicate"] == 1

        # 이제 상대 고객사(운수사) 등록
        c = models.Client(client_type="TRANSPORT", company_name="지연등록운수", biz_reg_no=COUNTERPART)
        db.add(c); db.commit(); cid = c.client_id

        # 재매칭 백필 → 미매칭이 자동 연결
        rm = client.post(API + "/rematch", headers=staff_headers)
        assert rm.status_code == 200, rm.text
        body = rm.json()
        assert body["relinked_client"] == 1 and body["still_unmatched"] == 0
        db.expire_all()
        inv2 = db.query(models.TaxInvoice).filter(
            models.TaxInvoice.approval_no.like("TESTIMP%")).first()
        assert inv2.matched_client_id == cid  # 재연결됨

        # 멱등 — 다시 돌리면 스캔 0
        rm2 = client.post(API + "/rematch", headers=staff_headers)
        assert rm2.json()["scanned"] == 0
    finally:
        _cleanup(db, cid)
        db.close()


def test_auto_rematch_on_client_create(client, staff_headers):
    """제안 3 — 미매칭 굳은 뒤 고객사를 '화면에서 등록'하면 버튼 없이 자동 연결."""
    db = models.SessionLocal()
    cid = None
    try:
        _cleanup(db, None)
        db.merge(models.Config(config_key="company_biz_reg_no", config_value=COMPANY))
        db.commit()
        html = _build_secure_mail(SAMPLE_XML, COMPANY)
        client.post(API + "/commit", headers=staff_headers, files=[_file(html)])
        inv = db.query(models.TaxInvoice).filter(
            models.TaxInvoice.approval_no.like("TESTIMP%")).first()
        assert inv.matched_client_id is None  # 미매칭

        # 고객사를 API(화면 경로)로 등록 → 자동 재매칭 트리거
        r = client.post("/api/v1/clients", headers=staff_headers, json={
            "client_type": "TRANSPORT", "company_name": "자동정합운수", "biz_reg_no": COUNTERPART})
        assert r.status_code == 201, r.text
        cid = r.json()["client_id"]
        db.expire_all()
        inv2 = db.query(models.TaxInvoice).filter(
            models.TaxInvoice.approval_no.like("TESTIMP%")).first()
        assert inv2.matched_client_id == cid  # 버튼 없이 자동 연결됨
    finally:
        _cleanup(db, cid)
        db.close()
