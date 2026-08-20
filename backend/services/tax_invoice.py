"""세금계산서 P2 — 홈택스 보안메일 복호화 + 국세청 표준 XML 파서.

실증된 레시피를 코드화한 순수 파싱 서비스(DB 미접촉). 홈택스가 발송하는
전자세금계산서 보안메일 HTML을 받아, 사업자번호(비밀번호)로 첨부를 복호화하고
국세청 표준(KEC) XML에서 승인번호·작성일시·금액·양측 사업자번호를 추출한다.

복호화 레시피 요약:
- 헤더(idCriHeader): base64 → 각 바이트 `^ 0x6b` → 텍스트(줄별 `키:값`).
- 키 = md5(사업자번호_숫자만) 16바이트.
- 암호 = CBC, IV=16×0x00, PKCS7. alg 1=AES / 2=SEED / 3=ARIA(미구현).
- 비번 검증 = HashKey 복호화 결과가 key.hex()와 일치.
- 첨부(idCriAttachContents{tagid}) = 복호화 → 다시 base64 → UTF-8 XML.

cryptography 49.0.0의 decrepit.SEED를 사용한다. bs4/lxml 없이 stdlib만 사용.
"""

import base64
import hashlib
import re
from decimal import Decimal
from typing import Dict, List, Optional
from xml.etree import ElementTree as ET

from cryptography.hazmat.decrepit.ciphers.algorithms import SEED
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from routers.common import normalize_biz_no

# 헤더 XOR 마스크 · CBC IV(16바이트 0)
_HEADER_XOR = 0x6B
_IV = b"\x00" * 16

# HTML hidden input 값 추출용 정규식 — id / value 순서 무관하게 매칭
_ATTACH_ID_RE = re.compile(r"idCriAttachContents(\d+)")


def _extract_input_value(html: str, input_id: str) -> Optional[str]:
    """`<input ... id="{input_id}" ... value="...">`에서 value 추출 (속성 순서 무관)."""
    # id 다음에 value가 오는 경우
    m = re.search(
        r'id="' + re.escape(input_id) + r'"[^>]*?value="([^"]*)"', html
    )
    if m:
        return m.group(1)
    # value가 id보다 앞에 오는 경우
    m = re.search(
        r'value="([^"]*)"[^>]*?id="' + re.escape(input_id) + r'"', html
    )
    if m:
        return m.group(1)
    return None


def extract_secure_mail(html: str) -> dict:
    """보안메일 HTML에서 헤더 base64 + 첨부맵(tagid→base64)을 추출.

    반환: {"header_b64": str|None, "attachments": {tagid(int): b64(str)},
           "pc_contents_b64": str|None}
    """
    header_b64 = _extract_input_value(html, "idCriHeader")
    pc_b64 = _extract_input_value(html, "idCriPcContents")

    attachments: Dict[int, str] = {}
    # 존재하는 idCriAttachContents{n} 태그 id들을 모두 수집
    for tagid in sorted({int(n) for n in _ATTACH_ID_RE.findall(html)}):
        val = _extract_input_value(html, "idCriAttachContents{0}".format(tagid))
        if val is not None:
            attachments[tagid] = val

    return {
        "header_b64": header_b64,
        "attachments": attachments,
        "pc_contents_b64": pc_b64,
    }


def decode_header(header_b64: str) -> dict:
    """헤더 base64 → XOR 0x6b 해독 → 줄별 `키:값` 파싱하여 dict 반환."""
    raw = base64.b64decode(header_b64)
    text = bytes(b ^ _HEADER_XOR for b in raw).decode("utf-8", errors="replace")
    result: Dict[str, str] = {}
    for line in text.replace("\r\n", "\n").split("\n"):
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip()
    return result


def password_key(bizno: str) -> bytes:
    """비밀번호 키 = md5(사업자번호_숫자만).digest() (16바이트)."""
    return hashlib.md5(normalize_biz_no(bizno).encode("utf-8")).digest()


def _decrypt(alg: int, ct_b64: str, key: bytes) -> bytes:
    """CBC(IV=0) + PKCS7 복호화. alg 1=AES / 2=SEED / 3=ARIA(미구현)."""
    if alg == 1:
        cipher_algo = algorithms.AES(key)
    elif alg == 2:
        cipher_algo = SEED(key)
    elif alg == 3:
        raise NotImplementedError("ARIA 알고리즘은 아직 지원하지 않습니다 (alg=3)")
    else:
        raise ValueError("알 수 없는 암호화 알고리즘: {0}".format(alg))

    ct = base64.b64decode(ct_b64)
    decryptor = Cipher(cipher_algo, modes.CBC(_IV)).decryptor()
    padded = decryptor.update(ct) + decryptor.finalize()
    unpadder = padding.PKCS7(cipher_algo.block_size).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def verify_password(header: dict, bizno: str) -> bool:
    """비번 검증 오라클 — HashKey 복호화 결과가 key.hex()와 일치하면 True."""
    hash_key = header.get("HashKey")
    if not hash_key:
        return False
    try:
        alg = int(header.get("ContentEncryptionAlgorithm", "2"))
        key = password_key(bizno)
        decrypted = _decrypt(alg, hash_key, key)
        return decrypted.decode("utf-8", errors="strict") == key.hex()
    except Exception:
        return False


def resolve_bizno(header: dict, candidates: List[str]) -> Optional[str]:
    """검증(오라클)을 통과하는 첫 후보 사업자번호를 반환. 없으면 None."""
    for candidate in candidates:
        if candidate and verify_password(header, candidate):
            return candidate
    return None


def decrypt_attachment_xml(header: dict, extracted: dict, key: bytes) -> str:
    """첨부 복호화 → (결과가 다시 base64) → 디코드 → UTF-8 XML 문자열."""
    alg = int(header.get("ContentEncryptionAlgorithm", "2"))
    tag = header.get("AttachFileTagID", "idCriAttachContents0")
    m = _ATTACH_ID_RE.search(tag)
    tagid = int(m.group(1)) if m else 0

    attachments = extracted.get("attachments", {})
    ct_b64 = attachments.get(tagid)
    if ct_b64 is None:
        raise ValueError("첨부(tagid={0})를 찾을 수 없습니다".format(tagid))

    decrypted = _decrypt(alg, ct_b64, key)
    xml_bytes = base64.b64decode(decrypted)
    return xml_bytes.decode("utf-8")


def _local(tag: str) -> str:
    """네임스페이스를 제거한 local-name 반환."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _iter_local(root, name: str):
    """트리 전체에서 local-name이 name인 요소를 문서 순서로 순회."""
    for el in root.iter():
        if _local(el.tag) == name:
            yield el


def _first_text(root, name: str) -> Optional[str]:
    for el in _iter_local(root, name):
        if el.text and el.text.strip():
            return el.text.strip()
    return None


def _to_int(text: Optional[str]) -> Optional[int]:
    if text is None:
        return None
    try:
        return int(Decimal(text.strip()))
    except Exception:
        return None


def parse_kec_xml(xml: str) -> dict:
    """국세청 표준(KEC) XML → 주요 필드 추출 (네임스페이스 무시, local-name 기준).

    - 공급자/공급받는자 사업자번호: Invoicer/Invoicee 래퍼 하위 party ID 우선,
      실패 시 문서순 10자리 숫자 ID 두 개.
    - IssueID=승인번호, IssueDateTime(14자리 우선)=작성일시,
      TypeCode(첫)·PurposeCode.
    - 금액: ChargeTotalAmount(공급가액)·TaxTotalAmount(세액)·GrandTotalAmount(합계).
    - 상호(NameText) 순서(선택).
    """
    root = ET.fromstring(xml)

    invoicer_reg_no: Optional[str] = None
    invoicee_reg_no: Optional[str] = None
    invoicer_name: Optional[str] = None
    invoicee_name: Optional[str] = None

    # 1) Invoicer/Invoicee 래퍼 하위의 party ID·상호(첫 NameText)를 구조적으로 추출
    for el in root.iter():
        lname = _local(el.tag)
        if lname in ("Invoicer", "InvoicerParty", "Invoicee", "InvoiceeParty"):
            reg = _first_id_10(el)
            name = _first_sub_text(el, "NameText")
            if lname.startswith("Invoicer"):
                if invoicer_reg_no is None and reg is not None:
                    invoicer_reg_no = reg
                if invoicer_name is None and name is not None:
                    invoicer_name = name
            elif lname.startswith("Invoicee"):
                if invoicee_reg_no is None and reg is not None:
                    invoicee_reg_no = reg
                if invoicee_name is None and name is not None:
                    invoicee_name = name

    # 2) 폴백 — 문서순 10자리 숫자 ID 두 개(첫=공급자, 둘째=공급받는자)
    if invoicer_reg_no is None or invoicee_reg_no is None:
        ten_digit_ids = [
            el.text.strip()
            for el in _iter_local(root, "ID")
            if el.text and re.fullmatch(r"\d{10}", el.text.strip())
        ]
        if invoicer_reg_no is None and len(ten_digit_ids) >= 1:
            invoicer_reg_no = ten_digit_ids[0]
        if invoicee_reg_no is None and len(ten_digit_ids) >= 2:
            invoicee_reg_no = ten_digit_ids[1]

    # 작성일시 — 14자리(YYYYMMDDHHMMSS) 우선, 없으면 첫 IssueDateTime
    issue_datetime = None
    for el in _iter_local(root, "IssueDateTime"):
        if el.text and re.fullmatch(r"\d{14}", el.text.strip()):
            issue_datetime = el.text.strip()
            break
    if issue_datetime is None:
        issue_datetime = _first_text(root, "IssueDateTime")

    names = [
        el.text.strip()
        for el in _iter_local(root, "NameText")
        if el.text and el.text.strip()
    ]

    return {
        "invoicer_reg_no": invoicer_reg_no,
        "invoicee_reg_no": invoicee_reg_no,
        "invoicer_name": invoicer_name,
        "invoicee_name": invoicee_name,
        "issue_id": _first_text(root, "IssueID"),
        "issue_datetime": issue_datetime,
        "type_code": _first_text(root, "TypeCode"),
        "purpose_code": _first_text(root, "PurposeCode"),
        "supply_amount": _to_int(_first_text(root, "ChargeTotalAmount")),
        "tax_amount": _to_int(_first_text(root, "TaxTotalAmount")),
        "total_amount": _to_int(_first_text(root, "GrandTotalAmount")),
        "names": names,
    }


def _first_id_10(el) -> Optional[str]:
    """요소 하위(자신 포함)에서 첫 10자리 숫자 ID를 찾아 반환."""
    for sub in el.iter():
        if _local(sub.tag) == "ID" and sub.text:
            t = sub.text.strip()
            if re.fullmatch(r"\d{10}", t):
                return t
    return None


def _first_sub_text(el, name: str) -> Optional[str]:
    """요소 하위(자신 포함)에서 local-name이 name인 첫 비어있지 않은 텍스트."""
    for sub in el.iter():
        if _local(sub.tag) == name and sub.text and sub.text.strip():
            return sub.text.strip()
    return None


def _issue_date_ymd(issue_datetime: Optional[str]) -> Optional[str]:
    """IssueDateTime(14자리 또는 그 이상) → 'YYYY-MM-DD'."""
    if not issue_datetime:
        return None
    digits = re.sub(r"\D", "", issue_datetime)
    if len(digits) >= 8:
        return "{0}-{1}-{2}".format(digits[0:4], digits[4:6], digits[6:8])
    return None


def parse_secure_mail(
    html: str, candidate_biznos: List[str], company_biz_no: str
) -> dict:
    """전체 파이프라인 — HTML → 복호화 → KEC XML 파싱 → 방향 판정.

    resolve 실패 시 {"ok": False, "reason": "password_unresolved"}.
    성공 시 승인번호·작성일시·금액·양측 사업자번호·방향 등을 담은 dict.
    방향: normalize(company)==invoicee → "매입", ==invoicer → "매출", 아니면 "미상".
    """
    extracted = extract_secure_mail(html)
    header_b64 = extracted.get("header_b64")
    if not header_b64:
        return {"ok": False, "reason": "header_missing"}

    # 불량 base64/헤더는 배치에서 한 파일 오류가 전체를 깨지 않게 사유로 반환
    try:
        header = decode_header(header_b64)
    except Exception:
        return {"ok": False, "reason": "header_decode_error"}

    matched = resolve_bizno(header, candidate_biznos)
    if matched is None:
        return {"ok": False, "reason": "password_unresolved"}

    # 비번은 오라클로 검증됐으나, 첨부/XML 손상 등 예외는 사유로 흡수(예외 전파 금지)
    try:
        key = password_key(matched)
        xml = decrypt_attachment_xml(header, extracted, key)
        parsed = parse_kec_xml(xml)
    except Exception:
        return {"ok": False, "reason": "decrypt_or_parse_error"}

    # 자사 사업자번호는 복수 가능(후시파트너스·후시제주랩 등) — str 또는 리스트 허용
    if isinstance(company_biz_no, str):
        company_set = {normalize_biz_no(company_biz_no)} if company_biz_no.strip() else set()
    else:
        company_set = {normalize_biz_no(c) for c in (company_biz_no or []) if c}
    company_set.discard("")

    invoicer = parsed.get("invoicer_reg_no")
    invoicee = parsed.get("invoicee_reg_no")
    invoicer_name = parsed.get("invoicer_name")
    invoicee_name = parsed.get("invoicee_name")

    if invoicee and normalize_biz_no(invoicee) in company_set:
        direction = "매입"  # 자사가 공급받는자
        counterpart, counterpart_name = invoicer, invoicer_name
    elif invoicer and normalize_biz_no(invoicer) in company_set:
        direction = "매출"  # 자사가 공급자
        counterpart, counterpart_name = invoicee, invoicee_name
    else:
        direction = "미상"
        counterpart, counterpart_name = None, None

    return {
        "ok": True,
        "direction": direction,
        "approval_no": parsed.get("issue_id"),
        "issue_date": _issue_date_ymd(parsed.get("issue_datetime")),
        "supply_amount": parsed.get("supply_amount"),
        "tax_amount": parsed.get("tax_amount"),
        "total_amount": parsed.get("total_amount"),
        "invoicer_reg_no": invoicer,
        "invoicee_reg_no": invoicee,
        "invoicer_name": invoicer_name,
        "invoicee_name": invoicee_name,
        "counterpart_reg_no": counterpart,
        "counterpart_name": counterpart_name,
        "type_code": parsed.get("type_code"),
        "purpose_code": parsed.get("purpose_code"),
        "matched_bizno": matched,
    }
