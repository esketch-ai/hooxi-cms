"""세금계산서 P2 — 보안메일 복호화 + KEC XML 파서 테스트 (합성 픽스처 정본).

실파일 의존 없이 SEED/AES로 직접 암호화한 보안메일 HTML을 만들어
복호화·오라클·XML 필드·방향 판정을 전건 검증한다. 실파일 파싱은
디렉터리가 있을 때만 도는 로컬 검증용(CI 스킵).
"""

import base64
import hashlib
import os

import pytest
from cryptography.hazmat.decrepit.ciphers.algorithms import SEED
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from services.tax_invoice import (
    _decrypt,
    decode_header,
    extract_secure_mail,
    parse_kec_xml,
    parse_secure_mail,
    password_key,
    verify_password,
)

_IV = b"\x00" * 16
_HEADER_XOR = 0x6B

# 합성 픽스처용 사업자번호
SUPPLIER_BIZNO = "1112233445"   # Invoicer(공급자)
BUYER_BIZNO = "5556677889"      # Invoicee(공급받는자)
WRONG_BIZNO = "9998887776"

APPROVAL_NO = "202607081026070896455535"
ISSUE_DATETIME = "20260708102607"


def _md5_key(bizno: str) -> bytes:
    return hashlib.md5(bizno.encode("utf-8")).digest()


def _encrypt(alg: int, plaintext: bytes, key: bytes) -> str:
    """CBC(IV=0)+PKCS7로 암호화 → base64. alg 1=AES / 2=SEED."""
    algo = algorithms.AES(key) if alg == 1 else SEED(key)
    padder = padding.PKCS7(algo.block_size).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algo, modes.CBC(_IV)).encryptor()
    ct = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(ct).decode("ascii")


def _kec_xml(
    invoicer=SUPPLIER_BIZNO,
    invoicee=BUYER_BIZNO,
    supply=16200000,
    tax=1620000,
    total=17820000,
    type_code="0101",
    purpose_code="01",
    issue_id=APPROVAL_NO,
    issue_dt=ISSUE_DATETIME,
) -> str:
    """최소 KEC XML (네임스페이스 포함, 구조적 Invoicer/Invoicee 래퍼)."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<TaxInvoice xmlns="urn:kec:standard:TaxInvoice">'
        "<ExchangedDocument>"
        "<IssueID>{issue_id}</IssueID>"
        "<IssueDateTime>{issue_dt}</IssueDateTime>"
        "<TypeCode>{type_code}</TypeCode>"
        "<PurposeCode>{purpose_code}</PurposeCode>"
        "</ExchangedDocument>"
        "<TaxInvoiceTradeSettlement>"
        "<InvoicerParty>"
        "<ID>{invoicer}</ID>"
        "<NameText>공급자상호</NameText>"
        "</InvoicerParty>"
        "<InvoiceeParty>"
        "<ID>{invoicee}</ID>"
        "<NameText>공급받는자상호</NameText>"
        "</InvoiceeParty>"
        "<ChargeTotalAmount>{supply}</ChargeTotalAmount>"
        "<TaxTotalAmount>{tax}</TaxTotalAmount>"
        "<GrandTotalAmount>{total}</GrandTotalAmount>"
        "</TaxInvoiceTradeSettlement>"
        "</TaxInvoice>"
    ).format(
        issue_id=issue_id,
        issue_dt=issue_dt,
        type_code=type_code,
        purpose_code=purpose_code,
        invoicer=invoicer,
        invoicee=invoicee,
        supply=supply,
        tax=tax,
        total=total,
    )


def _build_secure_mail_html(bizno: str, alg: int = 2, xml: str = None) -> str:
    """주어진 사업자번호(비번)로 암호화된 보안메일 HTML을 합성."""
    if xml is None:
        xml = _kec_xml()
    key = _md5_key(bizno)

    # 첨부 평문 = base64(xml) → 암호화 → base64
    attach_plain = base64.b64encode(xml.encode("utf-8"))
    attach_b64 = _encrypt(alg, attach_plain, key)

    # HashKey = 암호화(key.hex()) → base64
    hash_key_b64 = _encrypt(alg, key.hex().encode("utf-8"), key)

    header_text = (
        "ContentEncryptionAlgorithm:{alg}\r\n"
        "HashKey:{hk}\r\n"
        "AttachFileTagID:idCriAttachContents0"
    ).format(alg=alg, hk=hash_key_b64)
    header_raw = bytes(b ^ _HEADER_XOR for b in header_text.encode("utf-8"))
    header_b64 = base64.b64encode(header_raw).decode("ascii")

    return (
        "<html><body>"
        '<input type="hidden" id="idCriHeader" value="{header}">'
        '<input type="hidden" id="idCriAttachContents0" value="{attach}">'
        "</body></html>"
    ).format(header=header_b64, attach=attach_b64)


# ─────────────────────────── (e) 단위: _decrypt / 오라클 ───────────────────────────

def test_decrypt_pkcs7_roundtrip_seed():
    key = _md5_key(SUPPLIER_BIZNO)
    plain = b"hello-tax-invoice"
    ct = _encrypt(2, plain, key)
    assert _decrypt(2, ct, key) == plain


def test_decrypt_pkcs7_roundtrip_aes():
    key = _md5_key(SUPPLIER_BIZNO)
    plain = b"aes-branch-check"
    ct = _encrypt(1, plain, key)
    assert _decrypt(1, ct, key) == plain


def test_decrypt_aria_not_implemented():
    with pytest.raises(NotImplementedError):
        _decrypt(3, "AAAA", _md5_key(SUPPLIER_BIZNO))


def test_password_oracle():
    html = _build_secure_mail_html(SUPPLIER_BIZNO)
    header = decode_header(extract_secure_mail(html)["header_b64"])
    assert verify_password(header, SUPPLIER_BIZNO) is True
    assert verify_password(header, WRONG_BIZNO) is False
    # 하이픈 표기 차이도 normalize로 흡수
    assert verify_password(header, "111-22-33445") is True


def test_password_key_matches_md5():
    assert password_key("111-22-33445") == hashlib.md5(b"1112233445").digest()


# ─────────────────────────── XML 파서 단위 ───────────────────────────

def test_parse_kec_xml_fields():
    parsed = parse_kec_xml(_kec_xml())
    assert parsed["invoicer_reg_no"] == SUPPLIER_BIZNO
    assert parsed["invoicee_reg_no"] == BUYER_BIZNO
    assert parsed["issue_id"] == APPROVAL_NO
    assert parsed["issue_datetime"] == ISSUE_DATETIME
    assert parsed["type_code"] == "0101"
    assert parsed["purpose_code"] == "01"
    assert parsed["supply_amount"] == 16200000
    assert parsed["tax_amount"] == 1620000
    assert parsed["total_amount"] == 17820000
    assert parsed["names"] == ["공급자상호", "공급받는자상호"]


# ─────────────────────────── (a)(b)(c)(d) 전체 파이프라인 ───────────────────────────

def test_parse_secure_mail_success_seed():
    """(a) 정답 사업자번호(공급받는자)로 파싱 성공 — 매입 방향."""
    html = _build_secure_mail_html(BUYER_BIZNO)
    result = parse_secure_mail(
        html, candidate_biznos=[WRONG_BIZNO, BUYER_BIZNO], company_biz_no=BUYER_BIZNO
    )
    assert result["ok"] is True
    assert result["direction"] == "매입"
    assert result["approval_no"] == APPROVAL_NO
    assert result["issue_date"] == "2026-07-08"
    assert result["supply_amount"] == 16200000
    assert result["tax_amount"] == 1620000
    assert result["total_amount"] == 17820000
    assert result["invoicer_reg_no"] == SUPPLIER_BIZNO
    assert result["invoicee_reg_no"] == BUYER_BIZNO
    assert result["counterpart_reg_no"] == SUPPLIER_BIZNO
    assert result["matched_bizno"] == BUYER_BIZNO


def test_parse_secure_mail_wrong_password():
    """(b) 오답 후보만 주면 password_unresolved."""
    html = _build_secure_mail_html(BUYER_BIZNO)
    result = parse_secure_mail(
        html, candidate_biznos=[WRONG_BIZNO], company_biz_no=BUYER_BIZNO
    )
    assert result["ok"] is False
    assert result["reason"] == "password_unresolved"


def test_parse_secure_mail_direction_sales():
    """(c) company=invoicer면 매출 방향."""
    html = _build_secure_mail_html(SUPPLIER_BIZNO)
    result = parse_secure_mail(
        html, candidate_biznos=[SUPPLIER_BIZNO], company_biz_no=SUPPLIER_BIZNO
    )
    assert result["ok"] is True
    assert result["direction"] == "매출"
    assert result["counterpart_reg_no"] == BUYER_BIZNO


def test_parse_secure_mail_direction_unknown():
    """company가 양측 어디에도 없으면 미상."""
    html = _build_secure_mail_html(BUYER_BIZNO)
    result = parse_secure_mail(
        html, candidate_biznos=[BUYER_BIZNO], company_biz_no="0000000000"
    )
    assert result["ok"] is True
    assert result["direction"] == "미상"
    assert result["counterpart_reg_no"] is None


def test_parse_secure_mail_aes_fixture():
    """(d) AES(alg=1) 픽스처도 전 파이프라인 통과."""
    html = _build_secure_mail_html(BUYER_BIZNO, alg=1)
    result = parse_secure_mail(
        html, candidate_biznos=[BUYER_BIZNO], company_biz_no=BUYER_BIZNO
    )
    assert result["ok"] is True
    assert result["direction"] == "매입"
    assert result["total_amount"] == 17820000


# ─────────────────────────── 실파일(로컬 전용, CI 스킵) ───────────────────────────

_REAL_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "Docs", "세금계산서(html)"
)
_REAL_FILE = os.path.join(_REAL_DIR, "리빌벨류 → 후시파트너스.html")


@pytest.mark.skipif(
    not os.path.exists(_REAL_FILE), reason="실파일 없음(CI 스킵) — 로컬 검증용"
)
def test_parse_real_sample_reebill():
    with open(_REAL_FILE, "r", encoding="utf-8", errors="replace") as f:
        html = f.read()
    result = parse_secure_mail(
        html, candidate_biznos=["5298102298"], company_biz_no="5298102298"
    )
    assert result["ok"] is True
    assert result["approval_no"] == "202607081026070896455535"
    assert result["total_amount"] == 17820000
