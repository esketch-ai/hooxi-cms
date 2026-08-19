"""자산관리 보고(P2) — 운수사×사업 정산 요약 매트릭스 조회 + 엑셀 내보내기.

운수사별 예상지급액·감축량 요약과 사업별 드릴다운을 제공한다(매출/매입 제외 — 운수사
귀속 애매, 예상지급액 중심). 집계는 services.settlement_summary(단일 진실원)에 위임한다
(재계산 없음). 정산 확정/지급 상태는 P4 의존 → 이번엔 '예상지급액(정산예정)'만.

조회 의존성은 get_current_user 하나 — OBSERVER(경영전략실)는 정확매칭 화이트리스트
(/settlement-summary)로 통과, 외부역할(PARTNER/INVESTOR)은 원천 403(포털 격리).
내보내기(export)는 조회보다 좁은 require_role("MANAGER") 게이트 + 행 상한(400)·일일
반출 횟수(429)·워터마크·DATA_EXPORT 감사(금액 원문 미기록, R2-E6)로 대량 유출을 억제한다.
export 경로는 화이트리스트 미포함 → OBSERVER 자연 차단.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_permission, require_role
from models import ActivityHistory, Client, KakaoContact, Settlement, User, get_db
from routers import common
from routers.segments import can_receive_map
from services import email_service, integration_config, kakao_service
from services import settlement_notice as notice_service
from services import settlement_summary as summary_service
from services.audit_logger import AuditLogger
from services.market_rate import trailing_avg_rate
from services.report_sender import _config_template, resolve_recipients
from services.excel_export import (
    DAILY_EXPORT_LIMIT,
    MAX_EXPORT_ROWS,
    ColumnSpec,
    build_watermark,
    build_workbook,
    check_export_quota,
    enforce_row_limit,
    export_filename,
    xlsx_response,
)

router = APIRouter(prefix="/asset-report", tags=["asset-report"])

logger = logging.getLogger(__name__)

# 내보내기 균형 보안(EX-2) — 상한/일일한도 상수·가드는 services.excel_export 공용부를 재사용한다.
# (여기로 이름을 끌어와 endpoint별 monkeypatch·가독성을 유지: DAILY_EXPORT_LIMIT·MAX_EXPORT_ROWS)


@router.get("/settlement-summary", response_model=schemas.SettlementSummaryResponse)
def get_settlement_summary(
    client_id: Optional[str] = Query(None, description="운수사 필터(ProjectVehicle.client_id)"),
    client_type: Optional[str] = Query(None, description="고객사 구분 필터(Client.client_type)"),
    region: Optional[str] = Query(None, description="지역 필터(Client.region)"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """운수사×사업 정산 요약 매트릭스 — 운수사별 롤업 + 사업 드릴다운 + 전사 총계."""
    return summary_service.settlement_summary(
        db,
        client_id=client_id,
        client_type=client_type,
        region=region,
        avg6=trailing_avg_rate(db),
    )


# 내보내기 컬럼 규격(화면 컬럼과 정합) — 운수사×사업 평탄화 1행
_EXPORT_COLUMNS = [
    ColumnSpec("company_name", "운수사", "text"),
    ColumnSpec("project_name", "사업명", "text"),
    ColumnSpec("vehicle_count", "차량수", "number"),
    ColumnSpec("total_reduction", "총감축량", "number"),
    ColumnSpec("effective_reduction", "잔여반영감축량", "number"),
    ColumnSpec("expected_payout", "예상지급액", "money"),
    ColumnSpec("expected_revenue", "예상수익", "money"),
]


def _export_filter_summary(n, client_id, client_type, region):
    """감사 new_value — 행수 + 필터 요약(id·구분·지역)만. 금액·비밀값 원문 미기록(R2-E6)."""
    parts = []
    if client_id:
        parts.append("client={0}".format(client_id))
    if client_type:
        parts.append("type={0}".format(client_type))
    if region:
        parts.append("region={0}".format(region))
    return "rows={0}; filters={1}".format(n, ", ".join(parts) if parts else "none")


@router.get("/settlement-summary/export")
def export_settlement_summary(
    client_id: Optional[str] = Query(None, description="운수사 필터(ProjectVehicle.client_id)"),
    client_type: Optional[str] = Query(None, description="고객사 구분 필터(Client.client_type)"),
    region: Optional[str] = Query(None, description="지역 필터(Client.region)"),
    user: User = Depends(require_role("MANAGER")),
    db: Session = Depends(get_db),
):
    """정산 요약 엑셀 내보내기(EX-2) — 화면과 동일 필터의 운수사×사업 평탄화 전체 결과를 .xlsx로.

    조회(요약)보다 좁은 MANAGER 게이트 + 행 상한(400)·일일 반출 횟수(429)·워터마크·
    DATA_EXPORT 감사(금액 원문 미기록)로 대량 유출을 억제한다. 페이지네이션 없음(전체).
    """
    # 일일 반출 횟수 제한 — 공용 가드(오늘 KST DATA_EXPORT 감사 건수 재사용)
    check_export_quota(db, user, daily_limit=DAILY_EXPORT_LIMIT)

    data = summary_service.settlement_summary(
        db,
        client_id=client_id,
        client_type=client_type,
        region=region,
        avg6=trailing_avg_rate(db),
    )

    # 운수사×사업 평탄화 — 운수사-사업 1행(화면 드릴다운을 펼침)
    rows = []
    for item in data["items"]:
        for p in item["projects"]:
            rows.append(
                {
                    "company_name": item["company_name"],
                    "project_name": p["project_name"],
                    "vehicle_count": p["vehicle_count"],
                    "total_reduction": p["total_reduction"],
                    "effective_reduction": p["effective_reduction"],
                    "expected_payout": p["expected_payout"],
                    "expected_revenue": p["expected_revenue"],
                }
            )

    # 행 상한 — 공용 가드(무음 잘라내기 금지, 초과 시 400)
    enforce_row_limit(len(rows), max_rows=MAX_EXPORT_ROWS)

    # 합계행 = totals(화면 총계와 동일 원천)
    totals = data["totals"]
    total_row = {
        "vehicle_count": totals["participating_vehicle_count"],
        "total_reduction": totals["total_reduction"],
        "effective_reduction": totals["effective_reduction"],
        "expected_payout": totals["expected_payout"],
        "expected_revenue": totals["expected_revenue"],
    }

    content = build_workbook(
        _EXPORT_COLUMNS,
        rows,
        sheet_title="자산관리보고",
        watermark=build_watermark(user),
        total_row=total_row,
    )

    # 감사 — 반환 직전 기록(행수·필터 요약만, 금액·비밀값 원문 미기록) 후 커밋
    AuditLogger.log_action(
        db,
        user.user_id,
        "DATA_EXPORT",
        target_type="ASSET_REPORT",
        new_value=_export_filter_summary(len(rows), client_id, client_type, region),
    )
    db.commit()

    return xlsx_response(content, export_filename("자산관리보고"))


# ---------------------------------------------------------------------------
# 운수사 정산내역 능동 통지(P3) — 이메일 정산 명세 발송(수동) + 미리보기
#
# 외부(운수사)로 금액 정보를 보내므로 스코프 격리가 최우선 — 각 메일은 그 운수사
# 1건(client_item)만으로 렌더(services.settlement_notice.render_settlement_notice).
# 대상은 settlement_summary(단일 진실원) 롤업에서 (미지정) 제외분만. 감사는 카운트
# 요약만 기록하고 금액·수신 이메일 원문은 절대 남기지 않는다(R2-E6). 발송은 건별
# 실패 격리 + 건별 commit(segments._execute_send 관용구). master.write 게이트 +
# 화이트리스트 미포함 → OBSERVER·외부역할 자연 차단.
# ---------------------------------------------------------------------------
# 확정 통지(P4 증분3) 대상 판정용 — status가 확정 이상인 header만 롤업(예정=header 없음 제외).
# settlements 라우터 _TRANSITIONS와 동일 상태 문자열(코드 SETTLEMENT_STATUS) 사용.
_CONFIRMED_STATUSES = ("CONFIRMED", "BILLED", "COMPLETED")


def _confirmed_amount_map(db: Session, ids: list) -> dict:
    """운수사별 확정 정산액 롤업 — Σ tb_settlement.confirmed_amount(status 확정 이상).

    사업별 header를 운수사 단위로 합산(재계산 금지 — 동결값 confirmed_amount 사용).
    확정 header가 없는 운수사는 키 자체가 없다 → CONFIRMED 통지 대상에서 자연 제외.
    """
    if not ids:
        return {}
    rows = (
        db.query(Settlement.client_id, func.sum(Settlement.confirmed_amount))
        .filter(
            Settlement.client_id.in_(ids),
            Settlement.status.in_(_CONFIRMED_STATUSES),
        )
        .group_by(Settlement.client_id)
        .all()
    )
    return {cid: (float(amt) if amt is not None else None) for cid, amt in rows}


def _payout_source(notice_type: str, item: dict, confirmed_map: dict):
    """통지 유형별 금액 원천 — EXPECTED=live 예상지급액, CONFIRMED=확정 header 롤업."""
    if notice_type == "CONFIRMED":
        return confirmed_map.get(item["client_id"])
    return item.get("expected_payout")


def _sendable(payout, client_id: str, receivable: dict) -> bool:
    """실효 발송 대상 — 금액 산정 완료(원천값 not None) & 수신 가능(공통 수신자/주 담당자 이메일)."""
    return payout is not None and receivable.get(client_id, False)


# ── 카카오 알림톡 채널(P3 증분) ────────────────────────────────────────────────
# 정산 명세 '도착' 알림톡 — 본문에 금액을 포함하지 않는다(유출 리스크 최소, 상세는
# 메일/포털 확인). 수신번호는 KakaoContact(APPROVED·phone 有) 우선 → Client.main_contact_phone
# 폴백. 알림톡 미설정(SOLAPI 자격증명 or 템플릿 코드)이면 게이트로 전부 스킵한다.
# 이메일 흐름과 독립(채널별 실패격리) — 알림톡 실패는 이메일 발송을 되돌리지 않는다.
def _alimtalk_configured() -> bool:
    """알림톡 발송 가능 게이트 — SOLAPI 설정 + 정산 통지 템플릿 코드 존재."""
    return bool(
        kakao_service.is_configured_alimtalk()
        and integration_config.resolve("KAKAO_TEMPLATE_SETTLEMENT")
    )


def _alimtalk_phone_map(db: Session, clients: list) -> dict:
    """운수사별 알림톡 수신번호 — {client_id: phone or None}.

    KakaoContact(status APPROVED, phone 有, 최신 승인 우선) → 없으면 main_contact_phone.
    preview의 can_receive_alimtalk/count 판정에 사용(발송 없음).
    """
    ids = [c.client_id for c in clients]
    if not ids:
        return {}
    contacts = (
        db.query(KakaoContact)
        .filter(
            KakaoContact.client_id.in_(ids),
            KakaoContact.status == "APPROVED",
            KakaoContact.phone.isnot(None),
            KakaoContact.phone != "",
        )
        .order_by(KakaoContact.approved_at.desc())
        .all()
    )
    by_client = {}
    for ct in contacts:
        by_client.setdefault(ct.client_id, ct.phone)  # 최신 승인 연락처가 우선
    result = {}
    for c in clients:
        phone = by_client.get(c.client_id) or ((c.main_contact_phone or "").strip() or None)
        result[c.client_id] = phone
    return result


def _send_settlement_alimtalk(client: Client, to: Optional[str], *, notice_type: str):
    """정산 통지 알림톡 1건 발송 — 성공 True / 실패(예외 삼킴) False / 스킵 None.

    스코프 격리: 이 client 1건의 variables만 구성한다(타 운수사 정보 유입 불가).
    금액 미포함 — variables는 운수사명·기준일(오늘 KST)·통지유형만. 미설정/수신번호 부재는
    None(조용히 스킵)이라 이메일 흐름을 보존한다. 수신번호(to)는 호출부가 _alimtalk_phone_map
    (단일 진실원)에서 확정해 넘긴다 — 여기서 재조회하지 않는다. 발송 실패는 예외 종류와
    무관하게 삼켜 False: KakaoSendError뿐 아니라 httpx 타임아웃/연결오류·JSON 파싱오류 등이
    send 루프로 전파되면 HTTP 500·세션 롤백으로 채널 격리(이미 발송된 이메일 활동이력·나머지
    미발송)가 무너지므로 전면 포착한다. 로그는 예외 종류명만(전화·본문 미기록, R2-E6).
    """
    template_code = integration_config.resolve("KAKAO_TEMPLATE_SETTLEMENT")
    if not (kakao_service.is_configured_alimtalk() and template_code):
        return None  # 미설정 — 조용히 스킵(이메일 단독)
    if not to:
        return None  # 수신번호 없음 — 스킵

    variables = {
        "운수사명": client.company_name or "",
        "기준일": common.now_kst().strftime("%Y-%m-%d"),
        "통지유형": "확정" if notice_type == "CONFIRMED" else "예정",
    }
    try:
        kakao_service.send_alimtalk(to, template_code, variables)  # 금액 변수 없음
    except Exception as exc:  # 발송 실패 전면 삼킴 — 이메일 흐름·채널 격리 보존(500 방지)
        logger.warning("정산 통지 알림톡 발송 실패: %s", type(exc).__name__)
        return False
    return True


@router.post(
    "/settlement-notice/preview",
    response_model=schemas.SettlementNoticePreviewResponse,
)
def preview_settlement_notice(
    payload: schemas.SettlementNoticePreviewRequest = schemas.SettlementNoticePreviewRequest(),
    _: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """정산 명세 발송 미리보기 — 대상 운수사·수신 가능 여부·실효 발송 대상 수(발송 없음, 감사 없음).

    화면 필터(client_id/client_type/region)로 스코프한 settlement_summary 롤업에서 (미지정)
    제외분을 대상으로, can_receive_map(공통 수신자 또는 주 담당자 이메일 보유)과 sendable
    (expected_payout 산정 완료 & 수신 가능)을 계산한다. 이 목록의 sendable client_id들을
    프론트가 send.client_ids로 넘겨 미리보기==발송 대상을 고정한다(표류 차단).
    """
    data = summary_service.settlement_summary(
        db,
        client_id=payload.client_id,
        client_type=payload.client_type,
        region=payload.region,
    )
    targets = notice_service.settlement_notice_targets(data["items"])
    # CONFIRMED은 확정 header(confirmed_amount) 있는 운수사만 대상 — 미확정은 목록·sendable 제외.
    confirmed_map = (
        _confirmed_amount_map(db, [t["client_id"] for t in targets])
        if payload.notice_type == "CONFIRMED"
        else {}
    )
    if payload.notice_type == "CONFIRMED":
        targets = [t for t in targets if t["client_id"] in confirmed_map]
    # can_receive/to_count 판정은 Client 엔티티가 필요 — 대상 client_id 일괄 로드
    ids = [t["client_id"] for t in targets]
    clients = (
        db.query(Client).filter(Client.client_id.in_(ids)).all() if ids else []
    )
    receivable = can_receive_map(db, clients)
    to_counts = {c.client_id: len(resolve_recipients(db, c, sub=None)[0]) for c in clients}
    # 알림톡 채널 — 미설정(SOLAPI/템플릿)이면 게이트로 전부 false·count 0(수신번호 조회도 생략).
    alimtalk_on = _alimtalk_configured()
    phone_map = _alimtalk_phone_map(db, clients) if alimtalk_on else {}

    items = [
        schemas.SettlementNoticePreviewItem(
            client_id=t["client_id"],
            company_name=t["company_name"],
            # EXPECTED=live 예상지급액 / CONFIRMED=확정 header 롤업(고지 금액과 일치)
            expected_payout=_payout_source(payload.notice_type, t, confirmed_map),
            participating_vehicle_count=t.get("participating_vehicle_count") or 0,
            participating_project_count=t.get("participating_project_count") or 0,
            can_receive=receivable.get(t["client_id"], False),
            to_count=to_counts.get(t["client_id"], 0),
            can_receive_alimtalk=bool(alimtalk_on and phone_map.get(t["client_id"])),
            alimtalk_to_count=1 if (alimtalk_on and phone_map.get(t["client_id"])) else 0,
        )
        for t in targets
    ]
    sendable_count = sum(
        1
        for t in targets
        if _sendable(_payout_source(payload.notice_type, t, confirmed_map),
                     t["client_id"], receivable)
    )
    # 알림톡 실효 대상 — 금액 산정 완료(원천값 not None) & 수신번호 有 & 알림톡 설정(이메일과 동일한 금액 게이트).
    sendable_alimtalk_count = sum(
        1
        for t in targets
        if alimtalk_on
        and _payout_source(payload.notice_type, t, confirmed_map) is not None
        and phone_map.get(t["client_id"])
    )
    return schemas.SettlementNoticePreviewResponse(
        items=items, total=len(items), sendable_count=sendable_count,
        sendable_alimtalk_count=sendable_alimtalk_count,
    )


@router.post(
    "/settlement-notice/send",
    response_model=schemas.SettlementNoticeSendResult,
)
def send_settlement_notice(
    payload: schemas.SettlementNoticeSendRequest,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """정산 명세 이메일 발송(수동) — 대상 = 요청 client_ids ∩ sendable(없으면 sendable 전체).

    - 제목/본문은 payload.subject/body(고급옵션 오버라이드) 우선 → tb_config → 코드 기본값.
      오버라이드는 client별 변수만 정규식 치환하므로 스코프 유출이 없다(고지 문구 상시 부착).
    - Gmail 미설정 503 즉시 중단(활동 이력·감사 미생성 — report_sender 관용구).
    - 각 건: client_id 키 매칭으로 그 운수사 item만 렌더(스코프 격리 이중확인) →
      수신자 해석 → TO 0건 FAILED 격리(전체 중단 금지) → send_mail(html) → 성공 시
      활동 이력 EMAIL '[자동]' 적재 → 건별 commit(중간 실패 시에도 기왕 발송분 보존).
    - 감사 1건: SETTLEMENT_NOTICE_SEND/ASSET_REPORT, new_value=카운트 요약만
      (금액·수신 이메일·전화 원문 절대 미기록 — R2-E6).
    - channel(EMAIL|ALIMTALK|BOTH, 기본 EMAIL): ALIMTALK/BOTH면 각 대상에 정산 명세
      '도착' 알림톡(금액 미포함)을 병행. 채널별 독립 실패격리 — 알림톡 실패는 이메일
      발송을 되돌리지 않는다. 요청 채널이 전부 미설정이면 503(발송·감사 0).
    """
    # 채널 게이트(P3 증분) — 요청 채널만 설정 여부를 본다. EMAIL 포함이면 Gmail,
    # ALIMTALK 포함이면 알림톡(SOLAPI+템플릿). 요청 채널이 전부 미설정이면 503(발송·감사 0).
    # ALIMTALK 단독이면 Gmail 게이트를 건너뛴다(채널별 독립).
    want_email = payload.channel in ("EMAIL", "BOTH")
    want_alimtalk = payload.channel in ("ALIMTALK", "BOTH")
    email_ok = email_service.is_configured() if want_email else False
    alimtalk_ok = _alimtalk_configured() if want_alimtalk else False
    if not (email_ok or alimtalk_ok):
        if want_alimtalk and not want_email:
            detail = (
                "카카오 알림톡이 아직 설정되지 않았습니다. "
                "SOLAPI 자격증명과 정산 통지 템플릿(KAKAO_TEMPLATE_SETTLEMENT)을 설정한 뒤 "
                "다시 시도하세요. 발송 이력은 생성되지 않았습니다."
            )
        else:
            detail = (
                "이메일 발송 기능이 아직 설정되지 않았습니다. "
                "GMAIL_SENDER / GMAIL_APP_PASSWORD 환경변수를 설정한 뒤 다시 시도하세요 (CR-2). "
                "발송 이력은 생성되지 않았습니다."
            )
        raise HTTPException(status_code=503, detail=detail)

    data = summary_service.settlement_summary(db)
    targets = notice_service.settlement_notice_targets(data["items"])
    # client_id → item 매핑(스코프 격리 이중확인용 — 렌더 시 이 키로만 item을 가져온다)
    item_by_id = {t["client_id"]: t for t in targets}
    # CONFIRMED은 확정 header 있는 운수사만 대상 — 미확정은 item_by_id에서 제외(sendable 자연 미포함).
    confirmed_map = (
        _confirmed_amount_map(db, list(item_by_id))
        if payload.notice_type == "CONFIRMED"
        else {}
    )
    if payload.notice_type == "CONFIRMED":
        item_by_id = {cid: it for cid, it in item_by_id.items() if cid in confirmed_map}
    clients = {
        c.client_id: c
        for c in (
            db.query(Client).filter(Client.client_id.in_(list(item_by_id))).all()
            if item_by_id
            else []
        )
    }
    receivable = can_receive_map(db, list(clients.values()))
    # 채널별 실효 발송 대상 — 이메일: 금액 산정 완료 & 이메일 수신 가능. 알림톡: 금액 산정
    # 완료(동일 게이트) & 알림톡 수신번호 有 & 알림톡 설정. 알림톡 본문엔 금액이 없으나,
    # '통지할 정산이 존재'하는 동일 불변식(payout not None)을 채널 공통으로 유지한다.
    phone_map = _alimtalk_phone_map(db, list(clients.values())) if alimtalk_ok else {}
    email_sendable_ids = [
        cid
        for cid, it in item_by_id.items()
        if email_ok
        and _sendable(_payout_source(payload.notice_type, it, confirmed_map), cid, receivable)
    ]
    alimtalk_sendable_ids = [
        cid
        for cid, it in item_by_id.items()
        if alimtalk_ok
        and _payout_source(payload.notice_type, it, confirmed_map) is not None
        and phone_map.get(cid)
    ]

    # 대상 = 요청 client_ids ∩ sendable(요청 순서 보존·중복 제거), 없으면 sendable 전체.
    # 채널별 독립으로 잠근 뒤, 두 채널 대상의 합집합을 요약/요청 순서로 순회한다.
    def _lock(sendable_list):
        if payload.client_ids:
            sset = set(sendable_list)
            seen = set()
            return [
                cid
                for cid in payload.client_ids
                if cid in sset and not (cid in seen or seen.add(cid))
            ]
        return list(sendable_list)

    email_targets = set(_lock(email_sendable_ids))
    alimtalk_targets = set(_lock(alimtalk_sendable_ids))
    if payload.client_ids:
        _seen = set()
        order = [c for c in payload.client_ids if not (c in _seen or _seen.add(c))]
    else:
        order = list(item_by_id)
    target_ids = [c for c in order if c in email_targets or c in alimtalk_targets]

    # 제목/본문 = 요청 오버라이드(실무자 고급옵션) 우선, 미지정 시 tb_config, 없으면 코드 기본값.
    # 오버라이드도 render_settlement_notice에서 client별 변수만 주입(정규식 치환) → 스코프 유출 없음.
    # 통지 유형별 기본 템플릿·config 키 분기(EXPECTED=예정 명세 / CONFIRMED=확정 명세).
    if payload.notice_type == "CONFIRMED":
        subject_key, body_key = "settlement_notice_confirmed_subject", "settlement_notice_confirmed_body"
        default_subject = notice_service.DEFAULT_SETTLEMENT_NOTICE_CONFIRMED_SUBJECT
        default_body = notice_service.DEFAULT_SETTLEMENT_NOTICE_CONFIRMED_BODY
        activity_title = "{0} 정산 확정 명세 이메일 발송".format(common.AUTO_PREFIX)
        alimtalk_title = "{0} 정산 확정 명세 알림톡 발송".format(common.AUTO_PREFIX)
    else:
        subject_key, body_key = "settlement_notice_subject", "settlement_notice_body"
        default_subject = notice_service.DEFAULT_SETTLEMENT_NOTICE_SUBJECT
        default_body = notice_service.DEFAULT_SETTLEMENT_NOTICE_BODY
        activity_title = "{0} 정산 예정 명세 이메일 발송".format(common.AUTO_PREFIX)
        alimtalk_title = "{0} 정산 예정 명세 알림톡 발송".format(common.AUTO_PREFIX)
    subject_tpl = payload.subject or _config_template(db, subject_key, default_subject)
    body_tpl = payload.body or _config_template(db, body_key, default_body)
    now_kst = common.now_kst()

    sent = failed = 0  # 이메일 카운트(기존 계약 유지)
    alimtalk_sent = alimtalk_failed = 0  # 알림톡 카운트(채널별 독립)
    details = []
    for cid in target_ids:
        client = clients.get(cid)
        item = item_by_id.get(cid)
        do_email = cid in email_targets
        do_alimtalk = cid in alimtalk_targets
        email_result = alimtalk_result = None
        reason = None
        # 스코프 격리 이중확인 — client_id 키로 매칭한 item만 사용(불일치 시 방어적 스킵)
        if client is None or item is None or item.get("client_id") != cid:
            if do_email:
                failed += 1
                email_result = "FAILED"
            if do_alimtalk:
                alimtalk_failed += 1
                alimtalk_result = "FAILED"
            details.append(
                schemas.SettlementNoticeSendDetail(
                    client_id=cid, company_name=(client.company_name if client else ""),
                    result="FAILED", reason="대상 정합성 오류(운수사 매칭 실패)",
                    email_result=email_result, alimtalk_result=alimtalk_result,
                )
            )
            continue

        # ── 이메일 채널 ──────────────────────────────────────────────────────
        if do_email:
            to, cc = resolve_recipients(db, client, sub=None)
            if not to:
                failed += 1
                email_result = "FAILED"
                reason = "수신자 없음 — 공통 수신자 또는 주 담당자 이메일을 확인하세요 (R2-B5)"
            else:
                # CONFIRMED은 금액값을 확정 header 롤업으로 치환한 파생 item으로 렌더(원 summary item 불변).
                render_item = item
                if payload.notice_type == "CONFIRMED":
                    render_item = dict(item)
                    render_item["expected_payout"] = confirmed_map.get(cid)
                subject, html_body = notice_service.render_settlement_notice(
                    render_item,
                    subject_tpl=subject_tpl,
                    body_tpl=body_tpl,
                    notice_type=payload.notice_type,
                    now=now_kst,
                )
                try:
                    email_service.send_mail(
                        to=to, subject=subject, body=html_body, cc=cc or None,
                        reply_to=user.email, html=True,
                    )
                except Exception as exc:  # 건별 실패 격리 — 전체 중단 금지
                    failed += 1
                    email_result = "FAILED"
                    reason = str(exc)[:300]
                else:
                    sent += 1
                    email_result = "SENT"
                    # 활동 이력 EMAIL 자동 적재 (§9-3 — report_sender/segments와 동일 관용구)
                    db.add(
                        ActivityHistory(
                            client_id=cid, manager_id=user.user_id, created_by=user.user_id,
                            activity_date=now_kst, activity_type="EMAIL",
                            title=activity_title[:200],
                            content="수신자: {0}".format(", ".join(to + cc)),
                        )
                    )

        # ── 알림톡 채널(채널별 독립 실패격리 — 이메일 실패해도 시도) ──────────
        if do_alimtalk:
            # 수신번호는 phone_map(단일 진실원, sendable 판정과 동일값)에서 확정해 넘긴다(재조회 없음)
            ok = _send_settlement_alimtalk(
                client, phone_map.get(cid), notice_type=payload.notice_type
            )
            if ok is True:
                alimtalk_sent += 1
                alimtalk_result = "SENT"
                # 활동 이력 KAKAO 자동 적재 — 전화 원문 미기록(R2-E6)
                db.add(
                    ActivityHistory(
                        client_id=cid, manager_id=user.user_id, created_by=user.user_id,
                        activity_date=now_kst, activity_type="KAKAO",
                        title=alimtalk_title[:200],
                        content="정산 명세 도착 알림톡 발송",
                    )
                )
            elif ok is False:
                alimtalk_failed += 1
                alimtalk_result = "FAILED"
            else:
                # 미설정/수신번호 부재 등으로 스킵(대상 선정 게이트상 통상 미도달)
                alimtalk_result = "SKIPPED"

        db.commit()  # 건별 확정 — 발송 성공분 활동 이력 저장(중간 실패에도 기왕분 보존)
        # result(기존 계약) — EMAIL 요청 시 이메일 결과, ALIMTALK 단독이면 알림톡 결과
        result = email_result if do_email else alimtalk_result
        details.append(
            schemas.SettlementNoticeSendDetail(
                client_id=cid, company_name=client.company_name,
                result=result or "FAILED", reason=reason,
                email_result=email_result, alimtalk_result=alimtalk_result,
            )
        )

    # 감사 1건 — 카운트 요약만(금액·수신 이메일·전화 원문 절대 미기록, R2-E6)
    AuditLogger.log_action(
        db, user.user_id, "SETTLEMENT_NOTICE_SEND", target_type="ASSET_REPORT",
        new_value=(
            "targets={0}; sent={1}; failed={2}; type={3}; "
            "channel={4}; alimtalk_sent={5}; alimtalk_failed={6}".format(
                len(target_ids), sent, failed, payload.notice_type,
                payload.channel, alimtalk_sent, alimtalk_failed,
            )
        ),
    )
    db.commit()
    return schemas.SettlementNoticeSendResult(
        target_count=len(target_ids), sent=sent, failed=failed, details=details,
        alimtalk_sent=alimtalk_sent, alimtalk_failed=alimtalk_failed,
    )
