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


class _MatchContext:
    """복호화 후보·매칭 인덱스를 담는 1회 로드 컨텍스트 — 파일 루프 전체스캔 방지(DBA MED).

    candidates: 복호화 후보 사업자번호(자사 우선·정규화·중복제거)
    company: 자사 사업자번호(방향 판정용)
    client_by_biz/buyer_by_biz: 정규화 사업자번호 → 마스터(상대 매칭 O(1))
    """

    __slots__ = ("candidates", "company", "client_by_biz", "buyer_by_biz")

    def __init__(self, candidates, company, client_by_biz, buyer_by_biz):
        self.candidates = candidates
        self.company = company
        self.client_by_biz = client_by_biz
        self.buyer_by_biz = buyer_by_biz


def build_context(db) -> _MatchContext:
    """자사 + 전 고객사·투자사 사업자번호를 1회 로드해 후보 리스트·매칭 dict를 만든다."""
    company = company_biznos(db)
    seen = set(company)
    candidates: List[str] = list(company)  # 자사 우선
    client_by_biz: dict = {}
    buyer_by_biz: dict = {}
    for c in db.query(Client).filter(Client.biz_reg_no.isnot(None)).all():
        nb = normalize_biz_no(c.biz_reg_no)
        if not nb:
            continue
        client_by_biz.setdefault(nb, c)
        if nb not in seen:
            seen.add(nb)
            candidates.append(nb)
    for b in db.query(Buyer).filter(Buyer.biz_reg_no.isnot(None)).all():
        nb = normalize_biz_no(b.biz_reg_no)
        if not nb:
            continue
        buyer_by_biz.setdefault(nb, b)
        if nb not in seen:
            seen.add(nb)
            candidates.append(nb)
    return _MatchContext(candidates, company, client_by_biz, buyer_by_biz)


def candidate_biznos(db) -> List[str]:
    """복호화 후보 = 자사 + 전 고객사 + 전 투자사 사업자번호(정규화·중복제거, 자사 우선).

    하위호환용 — 다건 처리는 build_context()를 재사용해 전체스캔을 피한다.
    """
    return build_context(db).candidates


def analyze_html(
    db, html: str, filename: Optional[str] = None, ctx: Optional[_MatchContext] = None
) -> dict:
    """단일 HTML → 미리보기 항목(DB 무변경). 실패는 ok=False + reason.

    ctx를 주면 후보·매칭 인덱스를 재사용(다건 처리 성능). 없으면 1회 로드(단건 하위호환).
    """
    if ctx is None:
        ctx = build_context(db)
    parsed = tax_invoice.parse_secure_mail(html, ctx.candidates, ctx.company)
    item: dict = {"filename": filename, "ok": bool(parsed.get("ok"))}
    if not parsed.get("ok"):
        item["reason"] = parsed.get("reason")
        return item

    approval_no = parsed.get("approval_no")
    norm_cp = normalize_biz_no(parsed.get("counterpart_reg_no") or "")
    client = ctx.client_by_biz.get(norm_cp) if norm_cp else None
    buyer = ctx.buyer_by_biz.get(norm_cp) if norm_cp else None
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
    """[(filename, html)] → 미리보기 목록(DB 무변경). 매칭 컨텍스트 1회 로드로 전체스캔 방지."""
    ctx = build_context(db)
    return [analyze_html(db, html, filename, ctx) for filename, html in files]


def _to_date(iso: Optional[str]):
    if not iso:
        return None
    try:
        return date.fromisoformat(iso)
    except Exception:
        return None


def commit_html(
    db, html: str, actor_id: Optional[str] = None, project_id: Optional[str] = None,
    ctx: Optional[_MatchContext] = None,
) -> dict:
    """단일 HTML 적용 — 승인번호 unique로 멱등. result: created|duplicate|held."""
    item = analyze_html(db, html, ctx=ctx)
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
    """[(filename, html)] 적용 — 건별 격리, 카운트 요약. 매칭 컨텍스트 1회 로드."""
    ctx = build_context(db)
    created = duplicate = held = 0
    details = []
    for filename, html in files:
        r = commit_html(db, html, actor_id, project_id, ctx=ctx)
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


def rematch_unmatched(db) -> dict:
    """미매칭 세금계산서 재매칭 백필 — 나중에 등록된 고객사/투자사에 상대 사업자번호로 재연결.

    적재 시점에 마스터가 없어 matched_client_id·matched_buyer_id 둘 다 NULL로 굳은 행을,
    지금 마스터(Client·Buyer) 기준으로 counterpart_reg_no로 다시 찾아 FK를 채운다(재업로드 불요).
    멱등: 이미 매칭된 행은 건너뜀. analyze_html과 동일 매칭(자사 무관, 상대 사업자번호만).
    """
    ctx = build_context(db)
    rows = db.query(TaxInvoice).filter(
        TaxInvoice.matched_client_id.is_(None),
        TaxInvoice.matched_buyer_id.is_(None),
    ).all()
    relinked_client = relinked_buyer = 0
    for inv in rows:
        norm = normalize_biz_no(inv.counterpart_reg_no or "")
        if not norm:
            continue
        client = ctx.client_by_biz.get(norm)
        buyer = ctx.buyer_by_biz.get(norm)
        if client:
            inv.matched_client_id = client.client_id
            relinked_client += 1
        elif buyer:
            inv.matched_buyer_id = buyer.buyer_id
            relinked_buyer += 1
    return {
        "scanned": len(rows),
        "relinked_client": relinked_client,
        "relinked_buyer": relinked_buyer,
        "still_unmatched": len(rows) - relinked_client - relinked_buyer,
    }


def rematch_for_new_master(db, biz_reg_no, client_id=None, buyer_id=None) -> int:
    """새 마스터(고객사/투자사) 등록 시, 그 사업자번호의 미매칭 세금계산서를 자동 연결.

    create_client/create_buyer에서 호출 — 사용자가 재매칭 버튼을 누르지 않아도 지연 도착
    마스터에 미매칭이 자동으로 붙는다. 반환: 연결 건수(0이면 무변경). 커밋은 호출부 책임.
    """
    norm = normalize_biz_no(biz_reg_no or "")
    if not norm or not (client_id or buyer_id):
        return 0
    rows = db.query(TaxInvoice).filter(
        TaxInvoice.matched_client_id.is_(None),
        TaxInvoice.matched_buyer_id.is_(None),
        TaxInvoice.counterpart_reg_no.isnot(None),
    ).all()
    linked = 0
    for inv in rows:
        if normalize_biz_no(inv.counterpart_reg_no or "") != norm:
            continue
        if client_id:
            inv.matched_client_id = client_id
        else:
            inv.matched_buyer_id = buyer_id
        linked += 1
    return linked
