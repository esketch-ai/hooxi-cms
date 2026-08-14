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

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_permission, require_role
from models import ActivityHistory, Client, User, get_db
from routers import common
from routers.segments import can_receive_map
from services import email_service
from services import settlement_notice as notice_service
from services import settlement_summary as summary_service
from services.audit_logger import AuditLogger
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
        db, client_id=client_id, client_type=client_type, region=region
    )


# 내보내기 컬럼 규격(화면 컬럼과 정합) — 운수사×사업 평탄화 1행
_EXPORT_COLUMNS = [
    ColumnSpec("company_name", "운수사", "text"),
    ColumnSpec("project_name", "사업명", "text"),
    ColumnSpec("vehicle_count", "차량수", "number"),
    ColumnSpec("total_reduction", "총감축량", "number"),
    ColumnSpec("effective_reduction", "잔여반영감축량", "number"),
    ColumnSpec("expected_payout", "예상지급액", "money"),
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
        db, client_id=client_id, client_type=client_type, region=region
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
def _sendable(item: dict, receivable: dict) -> bool:
    """실효 발송 대상 — 예상지급액 산정 완료 & 수신 가능(공통 수신자/주 담당자 이메일)."""
    return item.get("expected_payout") is not None and receivable.get(item["client_id"], False)


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
    # can_receive/to_count 판정은 Client 엔티티가 필요 — 대상 client_id 일괄 로드
    ids = [t["client_id"] for t in targets]
    clients = (
        db.query(Client).filter(Client.client_id.in_(ids)).all() if ids else []
    )
    receivable = can_receive_map(db, clients)
    to_counts = {c.client_id: len(resolve_recipients(db, c, sub=None)[0]) for c in clients}

    items = [
        schemas.SettlementNoticePreviewItem(
            client_id=t["client_id"],
            company_name=t["company_name"],
            expected_payout=t.get("expected_payout"),
            participating_vehicle_count=t.get("participating_vehicle_count") or 0,
            participating_project_count=t.get("participating_project_count") or 0,
            can_receive=receivable.get(t["client_id"], False),
            to_count=to_counts.get(t["client_id"], 0),
        )
        for t in targets
    ]
    sendable_count = sum(1 for t in targets if _sendable(t, receivable))
    return schemas.SettlementNoticePreviewResponse(
        items=items, total=len(items), sendable_count=sendable_count
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
      (금액·수신 이메일 원문 절대 미기록 — R2-E6).
    """
    if not email_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "이메일 발송 기능이 아직 설정되지 않았습니다. "
                "GMAIL_SENDER / GMAIL_APP_PASSWORD 환경변수를 설정한 뒤 다시 시도하세요 (CR-2). "
                "발송 이력은 생성되지 않았습니다."
            ),
        )

    data = summary_service.settlement_summary(db)
    targets = notice_service.settlement_notice_targets(data["items"])
    # client_id → item 매핑(스코프 격리 이중확인용 — 렌더 시 이 키로만 item을 가져온다)
    item_by_id = {t["client_id"]: t for t in targets}
    clients = {
        c.client_id: c
        for c in (
            db.query(Client).filter(Client.client_id.in_(list(item_by_id))).all()
            if item_by_id
            else []
        )
    }
    receivable = can_receive_map(db, list(clients.values()))
    sendable_ids = [cid for cid, it in item_by_id.items() if _sendable(it, receivable)]

    # 대상 = 요청 client_ids ∩ sendable(요청 순서 보존·중복 제거), 없으면 sendable 전체
    if payload.client_ids:
        sendable_set = set(sendable_ids)
        seen = set()
        target_ids = [
            cid
            for cid in payload.client_ids
            if cid in sendable_set and not (cid in seen or seen.add(cid))
        ]
    else:
        target_ids = list(sendable_ids)

    # 제목/본문 = 요청 오버라이드(실무자 고급옵션) 우선, 미지정 시 tb_config, 없으면 코드 기본값.
    # 오버라이드도 render_settlement_notice에서 client별 변수만 주입(정규식 치환) → 스코프 유출 없음.
    subject_tpl = payload.subject or _config_template(
        db, "settlement_notice_subject", notice_service.DEFAULT_SETTLEMENT_NOTICE_SUBJECT
    )
    body_tpl = payload.body or _config_template(
        db, "settlement_notice_body", notice_service.DEFAULT_SETTLEMENT_NOTICE_BODY
    )
    now_kst = common.now_kst()

    sent = failed = 0
    details = []
    for cid in target_ids:
        client = clients.get(cid)
        item = item_by_id.get(cid)
        # 스코프 격리 이중확인 — client_id 키로 매칭한 item만 사용(불일치 시 방어적 스킵)
        if client is None or item is None or item.get("client_id") != cid:
            failed += 1
            details.append(
                schemas.SettlementNoticeSendDetail(
                    client_id=cid, company_name=(client.company_name if client else ""),
                    result="FAILED", reason="대상 정합성 오류(운수사 매칭 실패)",
                )
            )
            continue

        to, cc = resolve_recipients(db, client, sub=None)
        if not to:
            failed += 1
            details.append(
                schemas.SettlementNoticeSendDetail(
                    client_id=cid, company_name=client.company_name,
                    result="FAILED",
                    reason="수신자 없음 — 공통 수신자 또는 주 담당자 이메일을 확인하세요 (R2-B5)",
                )
            )
            continue

        subject, html_body = notice_service.render_settlement_notice(
            item, subject_tpl=subject_tpl, body_tpl=body_tpl, now=now_kst
        )
        try:
            email_service.send_mail(
                to=to, subject=subject, body=html_body, cc=cc or None,
                reply_to=user.email, html=True,
            )
        except Exception as exc:  # 건별 실패 격리 — 전체 중단 금지
            failed += 1
            details.append(
                schemas.SettlementNoticeSendDetail(
                    client_id=cid, company_name=client.company_name,
                    result="FAILED", reason=str(exc)[:300],
                )
            )
            continue

        sent += 1
        # 활동 이력 EMAIL 자동 적재 (§9-3 — report_sender/segments와 동일 관용구)
        db.add(
            ActivityHistory(
                client_id=cid, manager_id=user.user_id, created_by=user.user_id,
                activity_date=now_kst, activity_type="EMAIL",
                title="{0} 정산 예정 명세 이메일 발송".format(common.AUTO_PREFIX)[:200],
                content="수신자: {0}".format(", ".join(to + cc)),
            )
        )
        db.commit()  # 건별 확정 — 발송 성공 직후 활동 이력 저장
        details.append(
            schemas.SettlementNoticeSendDetail(
                client_id=cid, company_name=client.company_name, result="SENT",
            )
        )

    # 감사 1건 — 카운트 요약만(금액·수신 이메일 원문 절대 미기록, R2-E6)
    AuditLogger.log_action(
        db, user.user_id, "SETTLEMENT_NOTICE_SEND", target_type="ASSET_REPORT",
        new_value="targets={0}; sent={1}; failed={2}".format(len(target_ids), sent, failed),
    )
    db.commit()
    return schemas.SettlementNoticeSendResult(
        target_count=len(target_ids), sent=sent, failed=failed, details=details
    )
