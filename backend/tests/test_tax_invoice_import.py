"""세금계산서 자동반영(P4) — 매칭·미리보기·적용·멱등.

합성 보안메일(SEED 암호화)로 실파일 의존 없이 전 과정을 검증한다.
공유 SQLite 누수 방지를 위해 TEST 접두 식별자만 쓰고 정리한다.
"""

import base64
import hashlib

from cryptography.hazmat.decrepit.ciphers.algorithms import SEED
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, modes

import models
from services import tax_invoice_import as imp

_IV = b"\x00" * 16
COMPANY = "5298102298"       # 자사(후시)
COUNTERPART = "3541601931"   # 상대(공급자)
APPROVAL = "TESTIMP00000000000001"

SAMPLE_XML = (
    '<TaxInvoice xmlns="urn:kr:or:kec:standard:Tax">'
    "<TaxInvoiceDocument>"
    "<IssueID>" + APPROVAL + "</IssueID>"
    "<IssueDateTime>20260708215746</IssueDateTime>"
    "<TypeCode>0101</TypeCode><PurposeCode>02</PurposeCode>"
    "</TaxInvoiceDocument>"
    "<Invoicer><ID>" + COUNTERPART + "</ID><NameText>테스트공급자</NameText></Invoicer>"
    "<Invoicee><ID>" + COMPANY + "</ID><NameText>후시파트너스</NameText></Invoicee>"
    "<TaxTotalAmount>1620000</TaxTotalAmount>"
    "<ChargeTotalAmount>16200000</ChargeTotalAmount>"
    "<GrandTotalAmount>17820000</GrandTotalAmount>"
    "</TaxInvoice>"
)


def _seed_enc(data: bytes, key: bytes) -> bytes:
    pad = padding.PKCS7(SEED(key).block_size).padder()
    padded = pad.update(data) + pad.finalize()
    enc = Cipher(SEED(key), modes.CBC(_IV)).encryptor()
    return enc.update(padded) + enc.finalize()


def _build_secure_mail(xml: str, bizno: str) -> str:
    key = hashlib.md5(bizno.encode()).digest()
    attach_plain = base64.b64encode(xml.encode("utf-8"))  # 첨부 평문 = base64(xml)
    attach_b64 = base64.b64encode(_seed_enc(attach_plain, key)).decode()
    hashkey_b64 = base64.b64encode(_seed_enc(key.hex().encode(), key)).decode()
    header = (
        "ContentEncryptionAlgorithm:2\r\n"
        "HashKey:" + hashkey_b64 + "\r\n"
        "AttachFileTagID:idCriAttachContents0"
    )
    header_b64 = base64.b64encode(bytes(b ^ 0x6B for b in header.encode("utf-8"))).decode()
    return (
        '<input id="idCriHeader" value="' + header_b64 + '">'
        '<input id="idCriAttachContents0" value="' + attach_b64 + '">'
    )


def _cleanup(db, client_id):
    db.query(models.TaxInvoice).filter(
        models.TaxInvoice.approval_no.like("TESTIMP%")
    ).delete(synchronize_session=False)
    if client_id:
        db.query(models.Client).filter(models.Client.client_id == client_id).delete(
            synchronize_session=False
        )
    row = db.get(models.Config, "company_biz_reg_no")
    if row:
        row.config_value = ""
    db.commit()


def test_analyze_and_commit_idempotent(client):
    db = models.SessionLocal()
    created_client_id = None
    try:
        # 자사 사업자번호(하이픈 표기) config + 상대=운수사(Client) 시드
        db.merge(models.Config(config_key="company_biz_reg_no", config_value="529-81-02298"))
        c = models.Client(client_type="TRANSPORT", company_name="테스트공급자운수", biz_reg_no="354-16-01931")
        db.add(c)
        db.commit()
        created_client_id = c.client_id
        _cleanup_keep = None  # noqa

        html = _build_secure_mail(SAMPLE_XML, COMPANY)

        # 1) 미리보기 — DB 무변경
        item = imp.analyze_html(db, html, "테스트.html")
        assert item["ok"] is True
        assert item["direction"] == "매입"
        assert item["approval_no"] == APPROVAL
        assert item["supply_amount"] == 16200000
        assert item["tax_amount"] == 1620000
        assert item["total_amount"] == 17820000
        assert item["counterpart_reg_no"] == COUNTERPART
        assert item["matched_client_id"] == created_client_id  # 하이픈 무시 매칭
        assert item["is_duplicate"] is False
        assert db.query(models.TaxInvoice).filter_by(approval_no=APPROVAL).first() is None

        # 2) 적용 — 원장 생성
        r1 = imp.commit_html(db, html, actor_id="u-test")
        assert r1["result"] == "created"
        row = db.query(models.TaxInvoice).filter_by(approval_no=APPROVAL).first()
        assert row is not None
        assert row.direction == "매입"
        assert float(row.supply_amount) == 16200000
        assert row.matched_client_id == created_client_id
        assert str(row.issue_date) == "2026-07-08"

        # 3) 재적용 — 멱등(중복 스킵)
        r2 = imp.commit_html(db, html, actor_id="u-test")
        assert r2["result"] == "duplicate"
        assert db.query(models.TaxInvoice).filter_by(approval_no=APPROVAL).count() == 1

        # 4) 미리보기 재호출 — is_duplicate=True
        item2 = imp.analyze_html(db, html)
        assert item2["is_duplicate"] is True

        # 5) 오답만 후보면 password_unresolved (자사/상대 없는 config)
        row_cfg = db.get(models.Config, "company_biz_reg_no")
        row_cfg.config_value = "111-11-11111"
        db.commit()
        # 후보에서 정답이 빠지도록 상대 client도 제거
        db.query(models.Client).filter(models.Client.client_id == created_client_id).delete(
            synchronize_session=False
        )
        db.commit()
        held = imp.analyze_html(db, html)
        assert held["ok"] is False and held["reason"] == "password_unresolved"
    finally:
        _cleanup(db, created_client_id)
        db.close()


def test_direction_maechul_when_company_is_invoicer(client):
    """자사가 공급자면 매출 — 방향 판정 대칭 확인."""
    db = models.SessionLocal()
    try:
        db.merge(models.Config(config_key="company_biz_reg_no", config_value=COUNTERPART))
        db.commit()
        # COUNTERPART(자사) 공급자, COMPANY(상대) 받는자 → 매출
        html = _build_secure_mail(SAMPLE_XML, COUNTERPART)  # 비번=공급자(자사)
        item = imp.analyze_html(db, html)
        assert item["ok"] is True
        assert item["direction"] == "매출"
        assert item["counterpart_reg_no"] == COMPANY
    finally:
        _cleanup(db, None)
        db.close()
