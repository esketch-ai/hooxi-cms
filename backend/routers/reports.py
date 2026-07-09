"""월간 보고서 발송 관리 — SCR-12 (P1 핵심).

플로우(확정): 파일 업로드(tb_document 버전 적재) → 검토 → Gmail SMTP 발송(SENT)
→ tb_report_send_log 회차 적재 + 활동 이력 EMAIL "[자동]" 적재 → 고객 확인(CONFIRMED, 수기).

P3 확장: 구독 채널 KAKAO/BOTH + APPROVED 카카오 연락처(전화번호 보유) 존재 시
이메일 성공 후 SOLAPI 알림톡 시도 — KAKAO send_log(동일 seq) 적재, 성공 시 sent_channel=BOTH.
알림톡 실패해도 이메일 성공이면 SENT 유지(이메일 단독 폴백 — 기존 확정 정책).
"""

import json
import os
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

import schemas
from auth import JWT_SECRET, get_current_user, require_permission
from models import (
    ActivityHistory,
    Client,
    Document,
    KakaoContact,
    ReportDelivery,
    ReportRecipient,
    ReportSendLog,
    ReportSubscription,
    Schedule,
    User,
    get_db,
    utcnow,
)
from routers import common
from services import email_service, kakao_service, storage

router = APIRouter(prefix="/reports", tags=["reports"])

_SUMMARY_KEY_BY_STATUS = {
    "STANDBY": "standby",
    "WRITING": "writing",
    "REVIEW": "review",
    "SENT": "sent",
    "CONFIRMED": "confirmed",
    "CANCELED": "canceled",
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


VIEW_TOKEN_TTL_HOURS = 72  # 열람 링크 유효 시간 (확정: 서명 토큰 + 72시간 만료)


def create_view_token(doc_id: str, report_id: str) -> str:
    """열람 토큰 발급 — 자족(self-contained) JWT. GET /r/{token}에서 검증(DB 컬럼 불필요)."""
    payload = {
        "type": "view",
        "doc_id": doc_id,
        "report_id": report_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=VIEW_TOKEN_TTL_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _send_report_alimtalk(
    db: Session, delivery: ReportDelivery, client: Client, doc: Document,
    seq: int, month: int, user: User, reason: Optional[str],
) -> None:
    """이메일 성공 후 카카오 알림톡 시도 (구독 채널 KAKAO/BOTH).

    - APPROVED + 전화번호 보유 연락처가 없거나 알림톡 미설정이면 조용히 건너뜀(이메일 단독)
    - 성공: KAKAO send_log(동일 seq, SUCCESS) + sent_channel=BOTH
    - 실패: KAKAO send_log(동일 seq, FAIL) — 이메일 성공이므로 SENT 유지(폴백)
    """
    template_code = os.getenv("KAKAO_TEMPLATE_REPORT")
    if not (kakao_service.is_configured_alimtalk() and template_code):
        return

    contact = (
        db.query(KakaoContact)
        .filter(
            KakaoContact.client_id == delivery.client_id,
            KakaoContact.status == "APPROVED",
            KakaoContact.phone.isnot(None),
            KakaoContact.phone != "",
        )
        .order_by(KakaoContact.approved_at.desc())
        .first()
    )
    if contact is None:
        return

    view_url = "{0}/r/{1}".format(
        kakao_service.app_base_url(), create_view_token(doc.doc_id, delivery.report_id)
    )
    kakao_snapshot = json.dumps(
        {"kakao_to": contact.phone, "contact_name": contact.name}, ensure_ascii=False
    )
    try:
        kakao_service.send_alimtalk(
            to=contact.phone,
            template_code=template_code,
            variables={
                "고객사명": client.company_name,
                "월": str(month),
                "보고서유형": delivery.report_type,
            },
            buttons=[
                {
                    "buttonType": "WL",
                    "buttonName": "보고서 열람",
                    "linkMo": view_url,
                    "linkPc": view_url,
                }
            ],
        )
    except Exception:
        # 알림톡 실패 — 이메일 성공이므로 SENT 유지(이메일 단독 폴백)
        db.add(
            ReportSendLog(
                report_id=delivery.report_id, seq=seq, sent_doc_id=doc.doc_id,
                recipients=kakao_snapshot, channel="KAKAO", result="FAIL",
                sent_by=user.user_id, reason=reason,
            )
        )
        return

    db.add(
        ReportSendLog(
            report_id=delivery.report_id, seq=seq, sent_doc_id=doc.doc_id,
            recipients=kakao_snapshot, channel="KAKAO", result="SUCCESS",
            sent_by=user.user_id, reason=reason,
        )
    )
    delivery.sent_channel = "BOTH"


def _next_seq(db: Session, report_id: str) -> int:
    current = (
        db.query(func.max(ReportSendLog.seq))
        .filter(ReportSendLog.report_id == report_id)
        .scalar()
    )
    return (current or 0) + 1


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


@router.post("/generate", response_model=schemas.ReportGenerateResponse)
def generate_reports(
    period: Optional[str] = Query(None, description="YYYY-MM (기본: 당월)"),
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """당월 발송 대상 자동 생성 — tb_report_subscription(active=Y) 기반, 멱등.

    대상: 구독 활성 + 고객사 report_yn=Y + 계약 상태 ACTIVE.
    신규 생성 건은 마감일 REPORT_DUE 일정(SCR-11)도 함께 생성한다.
    """
    period = _resolve_period(period)
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
        manager_id = client.manager_id or user.user_id
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

    db.commit()
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
    file_url = storage.save_file(content, file.filename or "report", folder="reports/{0}".format(delivery.period))

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
    """보고서 이메일 발송 (CR-2: 대표 지메일).

    - Gmail 미설정 시 503 + 상태 변경 없음
    - 성공: SENT + tb_report_send_log(새 seq) + 활동 이력 EMAIL "[자동]" 적재
    - 실패: 직전 상태 유지 + FAIL 로그(새 seq) 적재 후 502
    """
    delivery = common.get_or_404(db, ReportDelivery, report_id, "보고서")
    if delivery.status == "CANCELED":
        raise HTTPException(status_code=409, detail="취소된 보고서는 발송할 수 없습니다")

    if not email_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "이메일 발송 기능이 아직 설정되지 않았습니다. "
                "GMAIL_SENDER / GMAIL_APP_PASSWORD 환경변수를 설정한 뒤 다시 시도하세요 (CR-2). "
                "보고서 상태는 변경되지 않았습니다."
            ),
        )

    client = common.get_or_404(db, Client, delivery.client_id, "고객사")

    # 발송 파일: 고정본(pinned) 우선, 없으면 최신본 (R2-B4)
    doc_id = delivery.pinned_doc_id or delivery.doc_id
    if not doc_id:
        raise HTTPException(status_code=409, detail="발송할 보고서 파일이 없습니다. 먼저 파일을 업로드하세요")
    doc = common.get_or_404(db, Document, doc_id, "보고서 파일")
    content = storage.read_file(doc.file_url)
    if content is None:
        raise HTTPException(status_code=500, detail="보고서 파일을 저장소에서 읽을 수 없습니다")

    # 수신자: tb_report_recipient(구독 지정분 + 공통분) → TO 0건이면 main_contact_email 폴백 (R2-B5)
    sub = (
        db.query(ReportSubscription)
        .filter(
            ReportSubscription.client_id == delivery.client_id,
            ReportSubscription.report_type == delivery.report_type,
        )
        .first()
    )
    recipients = (
        db.query(ReportRecipient).filter(ReportRecipient.client_id == delivery.client_id).all()
    )
    recipients = [
        r for r in recipients if r.sub_id is None or (sub and r.sub_id == sub.sub_id)
    ]
    to = [r.email for r in recipients if (r.cc_yn or "N") != "Y"]
    cc = [r.email for r in recipients if r.cc_yn == "Y"]
    if not to and client.main_contact_email:
        to = [client.main_contact_email]
    if not to:
        raise HTTPException(
            status_code=409,
            detail="TO 수신자가 없습니다. 수신자 등록 또는 고객사 주 담당자 이메일을 확인하세요 (R2-B5)",
        )

    year, month = int(delivery.period[:4]), int(delivery.period[5:7])
    subject = "[Hooxi Partners] {0} {1}월 {2} 보고서".format(
        client.company_name, month, delivery.report_type
    )
    body = (
        "안녕하세요, {0} 담당자님.\n\n"
        "{1}년 {2}월 {3} 보고서를 첨부와 같이 발송드립니다.\n"
        "확인 부탁드리며, 문의 사항은 본 메일에 회신해 주세요.\n\n"
        "감사합니다.\nHooxi Partners 드림"
    ).format(client.company_name, year, month, delivery.report_type)

    manager = db.get(User, delivery.manager_id) if delivery.manager_id else None
    reply_to = (manager.email if manager else None) or user.email
    filename = os.path.basename(doc.file_url) or "report"
    seq = _next_seq(db, report_id)
    recipients_snapshot = json.dumps({"to": to, "cc": cc}, ensure_ascii=False)
    reason = payload.reason if payload else None

    try:
        email_service.send_mail(
            to=to,
            subject=subject,
            body=body,
            cc=cc or None,
            attachments=[(filename, content, None)],
            reply_to=reply_to,
        )
    except email_service.EmailConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        # 실패: 직전 상태 유지 + FAIL 회차 기록 (R2-B3)
        db.add(
            ReportSendLog(
                report_id=report_id,
                seq=seq,
                sent_doc_id=doc.doc_id,
                recipients=recipients_snapshot,
                channel="EMAIL",
                result="FAIL",
                sent_by=user.user_id,
                reason=reason,
            )
        )
        db.commit()
        raise HTTPException(
            status_code=502,
            detail="이메일 발송에 실패했습니다. 잠시 후 재시도하세요 (상태는 변경되지 않았습니다): {0}".format(exc),
        )

    now = utcnow()
    db.add(
        ReportSendLog(
            report_id=report_id,
            seq=seq,
            sent_doc_id=doc.doc_id,
            recipients=recipients_snapshot,
            channel="EMAIL",
            result="SUCCESS",
            sent_by=user.user_id,
            reason=reason,
        )
    )
    delivery.status = "SENT"
    delivery.sent_at = now
    delivery.sent_channel = "EMAIL"

    # 카카오 알림톡 시도 — 구독 채널 KAKAO/BOTH (동일 seq KAKAO 행, 성공 시 BOTH)
    if sub and (sub.channel or "EMAIL") in ("KAKAO", "BOTH"):
        _send_report_alimtalk(db, delivery, client, doc, seq, month, user, reason)

    # 활동 이력 EMAIL 자동 적재 (§9-3)
    db.add(
        ActivityHistory(
            client_id=delivery.client_id,
            manager_id=user.user_id,
            created_by=user.user_id,
            activity_date=now,
            activity_type="EMAIL",
            title="{0} {1}월 {2} 보고서 이메일 발송".format(common.AUTO_PREFIX, month, delivery.report_type),
            content="수신자: {0}".format(", ".join(to + cc)),
        )
    )
    db.commit()

    return schemas.ReportSendResponse(
        message="보고서가 발송되었습니다",
        report_id=report_id,
        seq=seq,
        recipients=to + cc,
        sent_at=now,
    )


@router.put("/{report_id}/status", response_model=schemas.ReportRow)
def update_report_status(
    report_id: str,
    payload: schemas.ReportStatusUpdate,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """상태 변경 — CONFIRMED(수기 고객 확인)·CANCELED(사유 필수, R3-3) 포함."""
    delivery = common.get_or_404(db, ReportDelivery, report_id, "보고서")

    if payload.status == "CANCELED" and not (payload.canceled_reason or "").strip():
        raise HTTPException(status_code=422, detail="취소에는 사유(canceled_reason)가 필요합니다 (R3-3)")

    delivery.status = payload.status
    if payload.status == "CANCELED":
        delivery.canceled_reason = payload.canceled_reason
    elif payload.status == "CONFIRMED":
        delivery.confirmed_at = utcnow()
        delivery.confirm_basis = payload.confirm_basis or "수기"
    elif payload.status == "REVIEW":
        delivery.reviewed_by = user.user_id
        delivery.reviewed_at = utcnow()

    db.commit()
    db.refresh(delivery)
    return common.build_report_rows(db, [delivery])[0]
