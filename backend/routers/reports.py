"""월간 보고서 발송 관리 — SCR-12 (P1 핵심).

플로우(확정): 파일 업로드(tb_document 버전 적재) → 검토 → Gmail SMTP 발송(SENT)
→ tb_report_send_log 회차 적재 + 활동 이력 EMAIL "[자동]" 적재 → 고객 확인(CONFIRMED, 수기).

P3 확장: 구독 채널 KAKAO/BOTH + APPROVED 카카오 연락처(전화번호 보유) 존재 시
이메일 성공 후 SOLAPI 알림톡 시도 — KAKAO send_log(동일 seq) 적재, 성공 시 sent_channel=BOTH.
알림톡 실패해도 이메일 성공이면 SENT 유지(이메일 단독 폴백 — 기존 확정 정책).
"""

from calendar import monthrange
from datetime import date, datetime
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_permission
from models import (
    Client,
    Document,
    ReportDelivery,
    ReportSendLog,
    ReportSubscription,
    Schedule,
    User,
    get_db,
    utcnow,
)
from routers import common
from services import storage
from services.audit_logger import AuditLogger
from services.report_sender import SendPrecondition, send_report_core

router = APIRouter(prefix="/reports", tags=["reports"])

_SUMMARY_KEY_BY_STATUS = {
    "STANDBY": "standby",
    "WRITING": "writing",
    "REVIEW": "review",
    "APPROVED": "approved",
    "SENT": "sent",
    "CONFIRMED": "confirmed",
    "CANCELED": "canceled",
}

# 상태 전이 사전 — 서버 강제 (settlements._TRANSITIONS 준용).
# 감사 지적: 값 검증만 있고 전이 규칙이 없어 CANCELED→APPROVED 1콜이 허용되어
# 월초 배치가 취소 보고서를 자동 발송하는 오발송 경로가 열려 있었음.
# SENT는 발송 경로(send_report_core) 전용 — 이 사전에 대상으로 없어 직접 설정 불가.
_STATUS_TRANSITIONS = {
    "STANDBY": {"WRITING", "CANCELED"},
    "WRITING": {"REVIEW", "APPROVED", "CANCELED"},
    "REVIEW": {"WRITING", "APPROVED", "CANCELED"},
    "APPROVED": {"REVIEW", "WRITING", "CANCELED"},  # 승인 철회 허용
    "SENT": {"CONFIRMED"},
    "CONFIRMED": set(),  # 최종 상태 — 역행 금지
    "CANCELED": {"STANDBY"},  # 복원만 — 이후 정상 흐름 재진행
}


def _resolve_period(period: Optional[str]) -> str:
    if period is None:
        return common.current_period()
    return common.validate_period(period)


def _due_date_for(period: str, due_day: Optional[int]) -> date:
    """구독 마감일 → 당월 날짜 (짧은 달 말일 보정, 미지정 시 말일)."""
    year, month = int(period[:4]), int(period[5:7])
    last_day = monthrange(year, month)[1]
    return date(year, month, min(due_day or last_day, last_day))


@router.get("", response_model=schemas.ReportListResponse)
def list_reports(
    period: Optional[str] = Query(None, description="YYYY-MM (기본: 당월)"),
    status: Optional[str] = Query(None, description="상태 필터"),
    manager_id: Optional[str] = Query(None, description="담당자"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """월별 발송 현황 (행=고객사) + 요약 카운트."""
    period = _resolve_period(period)
    query = db.query(ReportDelivery).filter(ReportDelivery.period == period)
    if status:
        query = query.filter(ReportDelivery.status == status)
    if manager_id:
        query = query.filter(ReportDelivery.manager_id == manager_id)
    rows = query.order_by(ReportDelivery.due_date.asc(), ReportDelivery.created_at.asc()).all()

    summary = schemas.ReportSummary(target=len(rows))
    for r in rows:
        key = _SUMMARY_KEY_BY_STATUS.get(r.status)
        if key:
            setattr(summary, key, getattr(summary, key) + 1)

    return schemas.ReportListResponse(
        period=period, summary=summary, items=common.build_report_rows(db, rows)
    )


@router.get("/{report_id}", response_model=schemas.ReportDetailOut)
def get_report(
    report_id: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """행 확장 — 파일 버전 히스토리 + 발송 기록. (보고서 코멘트 테이블은 모델에 없음 — 빈 배열)"""
    delivery = common.get_or_404(db, ReportDelivery, report_id, "보고서")
    row = common.build_report_rows(db, [delivery])[0]

    docs = (
        db.query(Document)
        .filter(Document.report_id == report_id)
        .order_by(Document.version.desc(), Document.created_at.desc())
        .all()
    )
    logs = (
        db.query(ReportSendLog)
        .filter(ReportSendLog.report_id == report_id)
        .order_by(ReportSendLog.seq.desc())
        .all()
    )
    unames = common.user_name_map(db, [l.sent_by for l in logs])
    log_outs = [
        schemas.SendLogOut.model_validate(l, from_attributes=True).model_copy(
            update={"sent_by_name": unames.get(l.sent_by)}
        )
        for l in logs
    ]
    return schemas.ReportDetailOut(
        **row.model_dump(),
        documents=common.build_document_outs(db, docs),
        send_logs=log_outs,
        comments=[],
    )


def generate_for_period(db: Session, period: str, actor_id: str) -> Tuple[int, int]:
    """발송 대상 자동 생성 코어 — generate_reports(수동)·batch report-send(자동) 공유.

    대상: 구독 활성 + 고객사 report_yn=Y + 계약 상태 ACTIVE. (client, period, type) 멱등.
    신규 생성 건은 마감일 REPORT_DUE 일정(SCR-11)도 함께 생성한다. commit 포함.
    반환: (created, skipped).
    """
    subs = (
        db.query(ReportSubscription, Client)
        .join(Client, Client.client_id == ReportSubscription.client_id)
        .filter(
            ReportSubscription.active == "Y",
            Client.report_yn == "Y",
            Client.contract_status == "ACTIVE",
        )
        .all()
    )

    created = skipped = 0
    for sub, client in subs:
        exists = (
            db.query(ReportDelivery)
            .filter(
                ReportDelivery.client_id == sub.client_id,
                ReportDelivery.period == period,
                ReportDelivery.report_type == sub.report_type,
            )
            .first()
        )
        if exists:
            skipped += 1
            continue

        due = _due_date_for(period, sub.due_day)
        manager_id = client.manager_id or actor_id
        delivery = ReportDelivery(
            client_id=sub.client_id,
            period=period,
            report_type=sub.report_type,
            status="STANDBY",
            due_date=due,
            manager_id=manager_id,
        )
        db.add(delivery)
        # 마감일 캘린더 REPORT_DUE 자동 생성 (SCR-11 연동)
        db.add(
            Schedule(
                client_id=sub.client_id,
                manager_id=manager_id,
                schedule_type="REPORT_DUE",
                title="{0} 보고서 마감: {1} {2}".format(
                    common.AUTO_PREFIX, client.company_name, sub.report_type
                ),
                start_at=datetime(due.year, due.month, due.day, 9, 0, 0),
                memo="SCR-12 발송 대상 자동 생성",
                status="PLANNED",
            )
        )
        created += 1
        db.flush()  # PK(gen_uuid)는 flush 시점에 생성 — 감사 대상 ID 확보
        AuditLogger.log_action(
            db,
            actor_id,
            "REPORT_CREATE",
            target_type="REPORT_DELIVERY",
            target_id=delivery.report_id,
        )

    db.commit()
    return created, skipped


@router.post("/generate", response_model=schemas.ReportGenerateResponse)
def generate_reports(
    period: Optional[str] = Query(None, description="YYYY-MM (기본: 당월)"),
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """당월 발송 대상 자동 생성 — tb_report_subscription(active=Y) 기반, 멱등.

    본문은 generate_for_period 공유 코어(배치 report-send와 동일 로직) — 얇은 래퍼.
    """
    period = _resolve_period(period)
    created, skipped = generate_for_period(db, period, user.user_id)
    return schemas.ReportGenerateResponse(
        period=period,
        created=created,
        skipped=skipped,
        message="{0} 발송 대상 생성 완료 — 신규 {1}건, 기존 {2}건 유지".format(period, created, skipped),
    )


@router.post("/{report_id}/file", response_model=schemas.DocumentOut, status_code=201)
async def upload_report_file(
    report_id: str,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """보고서 파일 업로드 — tb_document 버전 적재, STANDBY면 WRITING으로 전환."""
    delivery = common.get_or_404(db, ReportDelivery, report_id, "보고서")
    if delivery.status in ("CANCELED",):
        raise HTTPException(status_code=409, detail="취소된 보고서에는 파일을 업로드할 수 없습니다")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="빈 파일은 업로드할 수 없습니다")
    # 업체별 서브 폴더: {업체명}/보고서/{YYYY-MM}/ (Dropbox 플랜 — 폴더 구조 규칙)
    report_client = db.get(Client, delivery.client_id) if delivery.client_id else None
    company = report_client.company_name if report_client else "_공용"
    file_url = storage.save_file(
        content,
        file.filename or "report",
        folder="{0}/보고서/{1}".format(company, delivery.period),
    )

    max_version = (
        db.query(func.max(Document.version)).filter(Document.report_id == report_id).scalar()
    )
    doc = Document(
        client_id=delivery.client_id,
        doc_type="REPORT",
        title=title or (file.filename or "보고서 파일"),
        file_url=file_url,
        version=(max_version or 0) + 1,
        report_id=report_id,
        uploaded_by=user.user_id,
    )
    db.add(doc)
    db.flush()

    delivery.doc_id = doc.doc_id  # 최신 표시용
    if delivery.status == "STANDBY":
        delivery.status = "WRITING"
    db.commit()
    db.refresh(doc)
    return common.build_document_outs(db, [doc])[0]


@router.post("/{report_id}/send", response_model=schemas.ReportSendResponse)
def send_report(
    report_id: str,
    payload: Optional[schemas.ReportSendRequest] = None,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """보고서 이메일 발송 (CR-2: 대표 지메일) — 본문은 services.report_sender 공유 코어.

    - Gmail 미설정 시 503 + 상태 변경 없음
    - 성공: SENT + tb_report_send_log(새 seq) + 활동 이력 EMAIL "[자동]" 적재
    - 실패: 직전 상태 유지 + FAIL 로그(새 seq) 적재 후 502
    """
    delivery = common.get_or_404(db, ReportDelivery, report_id, "보고서")
    if delivery.status == "CANCELED":
        raise HTTPException(status_code=409, detail="취소된 보고서는 발송할 수 없습니다")

    try:
        result = send_report_core(
            db, delivery, user.user_id, reason=payload.reason if payload else None
        )
    except SendPrecondition as exc:
        # 코어의 타입 예외 → 동일 상태코드·detail의 HTTPException (동작 불변)
        raise HTTPException(status_code=exc.code, detail=exc.detail)

    return schemas.ReportSendResponse(**result)


@router.put("/{report_id}/status", response_model=schemas.ReportRow)
def update_report_status(
    report_id: str,
    payload: schemas.ReportStatusUpdate,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """상태 변경 — CONFIRMED(수기 고객 확인)·CANCELED(사유 필수, R3-3) 포함.

    전이 사전(_STATUS_TRANSITIONS)으로 서버 강제 — 위반 시 409.
    SENT는 발송 경로(send/batch → send_report_core) 전용으로 직접 설정 불가.
    """
    delivery = common.get_or_404(db, ReportDelivery, report_id, "보고서")

    if payload.status == "CANCELED" and not (payload.canceled_reason or "").strip():
        raise HTTPException(status_code=422, detail="취소에는 사유(canceled_reason)가 필요합니다 (R3-3)")

    current = delivery.status or "STANDBY"
    if payload.status not in _STATUS_TRANSITIONS.get(current, set()):
        raise HTTPException(
            status_code=409,
            detail="'{0}' 상태에서 '{1}'(으)로 변경할 수 없습니다".format(current, payload.status),
        )

    # APPROVED(발송승인)는 발송할 파일이 확보된 상태여야 함 — 배치 자동 발송 전제
    if payload.status == "APPROVED" and not (delivery.pinned_doc_id or delivery.doc_id):
        raise HTTPException(
            status_code=409, detail="발송할 보고서 파일이 없습니다. 먼저 파일을 업로드하세요"
        )

    delivery.status = payload.status
    if payload.status == "CANCELED":
        delivery.canceled_reason = payload.canceled_reason
    else:
        # 취소 외 상태로 복귀 시 사유 잔존 방지 (QA 관찰 3)
        delivery.canceled_reason = None
    if payload.status == "CONFIRMED":
        delivery.confirmed_at = utcnow()
        delivery.confirm_basis = payload.confirm_basis or "수기"
    elif payload.status == "REVIEW":
        delivery.reviewed_by = user.user_id
        delivery.reviewed_at = utcnow()

    db.commit()
    db.refresh(delivery)
    return common.build_report_rows(db, [delivery])[0]
