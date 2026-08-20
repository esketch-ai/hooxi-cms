"""세금계산서 HTML 자동반영 — 매칭·미리보기·적용 (P4).

홈택스 보안메일 HTML을 파싱(services.tax_invoice)해 세금계산서 원장(tb_tax_invoice)에
적재한다. 자사 사업자번호(config company_biz_reg_no, 복수)와 고객사/투자사 사업자번호를
후보로 복호화하고, 상대(자사 아닌 쪽)를 운수사(Client)/투자사(Buyer) 마스터에 매칭한다.

- 미리보기(analyze)는 DB 무변경(파싱·매칭·중복판정만).
- 적용(commit)은 승인번호(unique)로 멱등 — 이미 있으면 중복 스킵.
"""

import re
from datetime import date
from typing import List, Optional, Tuple

from models import Buyer, Client, Config, TaxInvoice
from routers.common import normalize_biz_no
from services import client_folders, dropbox_storage, tax_invoice

_COMPANY_CONFIG_KEY = "company_biz_reg_no"
_SCAN_FOLDER_CONFIG_KEY = "tax_invoice_dropbox_folder"


def scan_folder_default(db) -> str:
    """스캔 기본 Dropbox 폴더(config tax_invoice_dropbox_folder). 미설정 시 ''."""
    row = db.get(Config, _SCAN_FOLDER_CONFIG_KEY)
    return ((row.config_value if row else "") or "").strip()


def scan_dropbox_html(folder_path: str, max_files: int = 500, max_depth: int = 6) -> List[Tuple[str, str]]:
    """Dropbox 폴더(하위 포함)에서 .html 파일을 내려받아 [(name, html)]. 저장소 루트 밖은 차단.

    Dropbox 미설정 시 dropbox_storage.DropboxConfigError를 상위로 전파(엔드포인트가 503).
    """
    root = dropbox_storage.root()
    base = client_folders.normalize_dropbox_path(folder_path)
    if root and not client_folders.is_within_folder(root, base):
        raise ValueError("스캔 폴더가 저장소 루트 밖입니다")

    files: List[Tuple[str, str]] = []

    def walk(path: str, depth: int) -> None:
        if depth > max_depth or len(files) >= max_files:
            return
        for e in dropbox_storage.list_folder(path):
            if len(files) >= max_files:
                break
            if e.get("is_dir"):
                walk(e["path_display"], depth + 1)
            elif str(e.get("name", "")).lower().endswith(".html"):
                content = dropbox_storage.download(e["path_display"])
                if content:
                    files.append((e["name"], content.decode("utf-8", errors="replace")))

    walk(base, 0)
    return files


def company_biznos(db) -> List[str]:
    """자사 사업자번호 목록(정규화) — config company_biz_reg_no를 콤마/줄/공백 분리."""
    row = db.get(Config, _COMPANY_CONFIG_KEY)
    raw = (row.config_value if row else "") or ""
    out: List[str] = []
    for part in re.split(r"[,\n\r\t ]+", raw):
        n = normalize_biz_no(part)
        if n and n not in out:
            out.append(n)
    return out


def candidate_biznos(db) -> List[str]:
    """복호화 후보 = 자사 + 전 고객사 + 전 투자사 사업자번호(정규화·중복제거, 자사 우선)."""
    out: List[str] = []

    def add(v: Optional[str]) -> None:
        n = normalize_biz_no(v or "")
        if n and n not in out:
            out.append(n)

    for n in company_biznos(db):
        add(n)
    for (b,) in db.query(Client.biz_reg_no).filter(Client.biz_reg_no.isnot(None)).all():
        add(b)
    for (b,) in db.query(Buyer.biz_reg_no).filter(Buyer.biz_reg_no.isnot(None)).all():
        add(b)
    return out


def _match_counterpart(db, counterpart_reg_no: Optional[str]) -> Tuple[Optional[Client], Optional[Buyer]]:
    """상대 사업자번호 → 운수사(Client)/투자사(Buyer) 매칭. 각 없으면 None."""
    if not counterpart_reg_no:
        return None, None
    norm = normalize_biz_no(counterpart_reg_no)
    if not norm:
        return None, None
    client = next(
        (c for c in db.query(Client).filter(Client.biz_reg_no.isnot(None)).all()
         if normalize_biz_no(c.biz_reg_no) == norm),
        None,
    )
    buyer = next(
        (b for b in db.query(Buyer).filter(Buyer.biz_reg_no.isnot(None)).all()
         if normalize_biz_no(b.biz_reg_no) == norm),
        None,
    )
    return client, buyer


def analyze_html(db, html: str, filename: Optional[str] = None) -> dict:
    """단일 HTML → 미리보기 항목(DB 무변경). 실패는 ok=False + reason."""
    parsed = tax_invoice.parse_secure_mail(html, candidate_biznos(db), company_biznos(db))
    item: dict = {"filename": filename, "ok": bool(parsed.get("ok"))}
    if not parsed.get("ok"):
        item["reason"] = parsed.get("reason")
        return item

    approval_no = parsed.get("approval_no")
    client, buyer = _match_counterpart(db, parsed.get("counterpart_reg_no"))
    is_duplicate = bool(
        approval_no
        and db.query(TaxInvoice).filter(TaxInvoice.approval_no == approval_no).first()
    )
    item.update(
        {
            "approval_no": approval_no,
            "direction": parsed.get("direction"),
            "issue_date": parsed.get("issue_date"),
            "invoicer_reg_no": parsed.get("invoicer_reg_no"),
            "invoicee_reg_no": parsed.get("invoicee_reg_no"),
            "invoicer_name": parsed.get("invoicer_name"),
            "invoicee_name": parsed.get("invoicee_name"),
            "counterpart_reg_no": parsed.get("counterpart_reg_no"),
            "counterpart_name": parsed.get("counterpart_name"),
            "supply_amount": parsed.get("supply_amount"),
            "tax_amount": parsed.get("tax_amount"),
            "total_amount": parsed.get("total_amount"),
            "type_code": parsed.get("type_code"),
            "purpose_code": parsed.get("purpose_code"),
            "matched_client_id": client.client_id if client else None,
            "matched_client_name": client.company_name if client else None,
            "matched_buyer_id": buyer.buyer_id if buyer else None,
            "matched_buyer_name": buyer.name if buyer else None,
            "is_duplicate": is_duplicate,
        }
    )
    return item


def analyze_files(db, files: List[Tuple[str, str]]) -> List[dict]:
    """[(filename, html)] → 미리보기 목록(DB 무변경)."""
    return [analyze_html(db, html, filename) for filename, html in files]


def _to_date(iso: Optional[str]):
    if not iso:
        return None
    try:
        return date.fromisoformat(iso)
    except Exception:
        return None


def commit_html(db, html: str, actor_id: Optional[str] = None, project_id: Optional[str] = None) -> dict:
    """단일 HTML 적용 — 승인번호 unique로 멱등. result: created|duplicate|held."""
    item = analyze_html(db, html)
    if not item.get("ok"):
        return {"result": "held", "reason": item.get("reason")}
    approval_no = item.get("approval_no")
    if not approval_no:
        return {"result": "held", "reason": "no_approval_no"}
    if item.get("is_duplicate"):
        return {"result": "duplicate", "approval_no": approval_no}

    inv = TaxInvoice(
        approval_no=approval_no,
        direction=item.get("direction"),
        invoicer_reg_no=item.get("invoicer_reg_no"),
        invoicee_reg_no=item.get("invoicee_reg_no"),
        invoicer_name=item.get("invoicer_name"),
        invoicee_name=item.get("invoicee_name"),
        counterpart_reg_no=item.get("counterpart_reg_no"),
        counterpart_name=item.get("counterpart_name"),
        issue_date=_to_date(item.get("issue_date")),
        supply_amount=item.get("supply_amount"),
        tax_amount=item.get("tax_amount"),
        total_amount=item.get("total_amount"),
        type_code=item.get("type_code"),
        purpose_code=item.get("purpose_code"),
        matched_client_id=item.get("matched_client_id"),
        matched_buyer_id=item.get("matched_buyer_id"),
        project_id=project_id,
        source="HTML_IMPORT",
        created_by=actor_id,
    )
    db.add(inv)
    try:
        db.commit()
    except Exception:
        db.rollback()  # 승인번호 unique 경합 → 중복으로 흡수
        return {"result": "duplicate", "approval_no": approval_no}
    return {"result": "created", "approval_no": approval_no, "tax_invoice_id": inv.tax_invoice_id}


def commit_files(db, files: List[Tuple[str, str]], actor_id: Optional[str] = None, project_id: Optional[str] = None) -> dict:
    """[(filename, html)] 적용 — 건별 격리, 카운트 요약."""
    created = duplicate = held = 0
    details = []
    for filename, html in files:
        r = commit_html(db, html, actor_id, project_id)
        details.append({"filename": filename, **r})
        if r["result"] == "created":
            created += 1
        elif r["result"] == "duplicate":
            duplicate += 1
        else:
            held += 1
    return {
        "total": len(files),
        "created": created,
        "duplicate": duplicate,
        "held": held,
        "details": details,
    }
