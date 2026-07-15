"""보고서 발송 코어 서비스 — SCR-12 send_report 본문 분리 (배치 자동 발송 재사용용).

routers/reports.py의 수동 발송과 배치 자동 발송이 같은 로직을 공유한다.
HTTP 계층 의존을 없애기 위해 HTTPException 대신 SendPrecondition(code, detail)을 던지고,
호출부(라우터)가 동일한 상태코드·문구의 HTTPException으로 변환한다(동작 불변).

- Gmail 미설정 시 503 + 상태 변경 없음
- 성공: SENT + tb_report_send_log(새 seq) + 활동 이력 EMAIL "[자동]" 적재
- 실패: 직전 상태 유지 + FAIL 로그(새 seq) 적재 후 502
- P3: 구독 채널 KAKAO/BOTH면 이메일 성공 후 알림톡 시도(실패해도 SENT 유지 — 이메일 단독 폴백)
"""

import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import jwt
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth import JWT_SECRET
from models import (
    ActivityHistory,
    Client,
    Config,
    Document,
    KakaoContact,
    ReportDelivery,
    ReportRecipient,
    ReportSendLog,
    ReportSubscription,
    User,
    utcnow,
)
from routers import common
from services import email_service, integration_config, kakao_service, storage
from services.audit_logger import AuditLogger


class SendPrecondition(Exception):
    """발송 전제조건 미충족/발송 실패 — HTTP 계층에서 동일 상태코드·detail로 변환.

    code: HTTP 상태코드(404 대상 없음, 409 파일/수신자 없음, 500 저장소 읽기 실패,
    502 발송 실패, 503 Gmail 미설정).
    """

    def __init__(self, code: int, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


VIEW_TOKEN_TTL_HOURS = 72  # 열람 링크 유효 시간 (확정: 서명 토큰 + 72시간 만료)

# 메일 템플릿 코드 기본값 — 기본값 렌더 결과는 기존 하드코딩 발송 문구와 동일해야 함 (회귀 없음).
# tb_config(report_mail_subject/report_mail_body) 미저장 시 이 값이 유효값이다 (routers/config.py KNOWN_DEFAULTS 공유).
DEFAULT_REPORT_MAIL_SUBJECT = "[Hooxi Partners] {고객사명} {월}월 {보고서유형} 보고서"
DEFAULT_REPORT_MAIL_BODY = (
    "안녕하세요, {고객사명} 담당자님.\n\n"
    "{연도}년 {월}월 {보고서유형} 보고서를 첨부와 같이 발송드립니다.\n"
    "확인 부탁드리며, 문의 사항은 본 메일에 회신해 주세요.\n\n"
    "감사합니다.\nHooxi Partners 드림"
)


def _config_template(db: Session, key: str, default: str) -> str:
    """tb_config 문자열 템플릿 오버라이드 존중 — 파싱 실패/빈 값이면 코드 기본값 (funnel_mapping 패턴)."""
    row = db.get(Config, key)
    if row and row.config_value:
        try:
            parsed = json.loads(row.config_value)
            if isinstance(parsed, str) and parsed.strip():
                return parsed
        except (ValueError, TypeError):
            pass
    return default


def render_mail(
    db: Session,
    delivery: ReportDelivery,
    client: Client,
    subscription: Optional[ReportSubscription],
) -> Tuple[str, str]:
    """보고서 메일 제목·본문 렌더 — (구독 오버라이드 → tb_config 전역 → 코드 기본값) 순.

    치환 변수: {고객사명} {기간}(YYYY-MM) {연도} {월} {보고서유형} {담당자명}.
    정규식 치환이라 미지원 {...}는 원문 유지 — str.format이면 KeyError로 발송이 막히므로 금지.
    """
    year, month = int(delivery.period[:4]), int(delivery.period[5:7])
    manager_id = delivery.manager_id or client.manager_id
    manager = db.get(User, manager_id) if manager_id else None
    variables = {
        "고객사명": client.company_name or "",
        "기간": delivery.period or "",
        "연도": str(year),
        "월": str(month),
        "보고서유형": (subscription.report_type if subscription else None)
        or delivery.report_type
        or "",
        "담당자명": (manager.name if manager else None) or "",
    }

    sub_subject = (subscription.mail_subject or "").strip() if subscription else ""
    sub_body = (subscription.mail_body or "").strip() if subscription else ""
    subject_tpl = (subscription.mail_subject if sub_subject else None) or _config_template(
        db, "report_mail_subject", DEFAULT_REPORT_MAIL_SUBJECT
    )
    body_tpl = (subscription.mail_body if sub_body else None) or _config_template(
        db, "report_mail_body", DEFAULT_REPORT_MAIL_BODY
    )

    def _render(template: str) -> str:
        return re.sub(
            r"\{([^{}]+)\}",
            lambda m: variables.get(m.group(1), m.group(0)),
            template,
        )

    return _render(subject_tpl), _render(body_tpl)


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
    seq: int, month: int, actor_id: str, reason: Optional[str],
) -> None:
    """이메일 성공 후 카카오 알림톡 시도 (구독 채널 KAKAO/BOTH).

    - APPROVED + 전화번호 보유 연락처가 없거나 알림톡 미설정이면 조용히 건너뜀(이메일 단독)
    - 성공: KAKAO send_log(동일 seq, SUCCESS) + sent_channel=BOTH
    - 실패: KAKAO send_log(동일 seq, FAIL) — 이메일 성공이므로 SENT 유지(폴백)
    """
    template_code = integration_config.resolve("KAKAO_TEMPLATE_REPORT")
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
                sent_by=actor_id, reason=reason,
            )
        )
        return

    db.add(
        ReportSendLog(
            report_id=delivery.report_id, seq=seq, sent_doc_id=doc.doc_id,
            recipients=kakao_snapshot, channel="KAKAO", result="SUCCESS",
            sent_by=actor_id, reason=reason,
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


def send_report_core(
    db: Session, delivery: ReportDelivery, actor_id: str, reason: Optional[str] = None
) -> dict:
    """보고서 이메일 발송 코어 (CR-2: 대표 지메일) — send_report 본문 그대로 이동.

    호출 전 검사(라우터/배치 책임): delivery 존재(404)·CANCELED 여부(409).
    실패 경로 트랜잭션 순서 보존: FAIL 로그 적재 → commit → SendPrecondition(502) 재-raise.
    반환 dict는 schemas.ReportSendResponse 필드와 1:1 대응.
    """
    report_id = delivery.report_id

    if not email_service.is_configured():
        raise SendPrecondition(
            503,
            (
                "이메일 발송 기능이 아직 설정되지 않았습니다. "
                "GMAIL_SENDER / GMAIL_APP_PASSWORD 환경변수를 설정한 뒤 다시 시도하세요 (CR-2). "
                "보고서 상태는 변경되지 않았습니다."
            ),
        )

    # common.get_or_404와 동일한 404 detail 문구 유지 (동작 불변)
    client = db.get(Client, delivery.client_id) if delivery.client_id else None
    if client is None:
        raise SendPrecondition(404, "고객사을(를) 찾을 수 없습니다")

    # 발송 파일: 고정본(pinned) 우선, 없으면 최신본 (R2-B4)
    doc_id = delivery.pinned_doc_id or delivery.doc_id
    if not doc_id:
        raise SendPrecondition(409, "발송할 보고서 파일이 없습니다. 먼저 파일을 업로드하세요")
    doc = db.get(Document, doc_id)
    if doc is None:
        raise SendPrecondition(404, "보고서 파일을(를) 찾을 수 없습니다")
    content = storage.read_file(doc.file_url)
    if content is None:
        raise SendPrecondition(500, "보고서 파일을 저장소에서 읽을 수 없습니다")

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
        raise SendPrecondition(
            409,
            "TO 수신자가 없습니다. 수신자 등록 또는 고객사 주 담당자 이메일을 확인하세요 (R2-B5)",
        )

    month = int(delivery.period[5:7])
    # 제목·본문 템플릿 렌더 — 구독 오버라이드 → tb_config 전역 → 코드 기본값 (B3/B4)
    subject, body = render_mail(db, delivery, client, sub)

    manager = db.get(User, delivery.manager_id) if delivery.manager_id else None
    actor = db.get(User, actor_id) if actor_id else None
    reply_to = (manager.email if manager else None) or (actor.email if actor else None)
    filename = os.path.basename(doc.file_url) or "report"
    seq = _next_seq(db, report_id)
    recipients_snapshot = json.dumps({"to": to, "cc": cc}, ensure_ascii=False)

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
        raise SendPrecondition(503, str(exc))
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
                sent_by=actor_id,
                reason=reason,
            )
        )
        db.commit()
        raise SendPrecondition(
            502,
            "이메일 발송에 실패했습니다. 잠시 후 재시도하세요 (상태는 변경되지 않았습니다): {0}".format(exc),
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
            sent_by=actor_id,
            reason=reason,
        )
    )
    delivery.status = "SENT"
    delivery.sent_at = now
    delivery.sent_channel = "EMAIL"

    # 카카오 알림톡 시도 — 구독 채널 KAKAO/BOTH (동일 seq KAKAO 행, 성공 시 BOTH)
    if sub and (sub.channel or "EMAIL") in ("KAKAO", "BOTH"):
        _send_report_alimtalk(db, delivery, client, doc, seq, month, actor_id, reason)

    # 활동 이력 EMAIL 자동 적재 (§9-3)
    db.add(
        ActivityHistory(
            client_id=delivery.client_id,
            manager_id=actor_id,
            created_by=actor_id,
            activity_date=now,
            activity_type="EMAIL",
            title="{0} {1}월 {2} 보고서 이메일 발송".format(common.AUTO_PREFIX, month, delivery.report_type),
            content="수신자: {0}".format(", ".join(to + cc)),
        )
    )
    # 감사 로그는 커밋 전에 적재해야 함께 저장된다 (커밋 후 add는 유실)
    AuditLogger.log_action(
        db,
        actor_id,
        "REPORT_SEND",
        target_type="REPORT_DELIVERY",
        target_id=report_id,
    )
    db.commit()

    return {
        "message": "보고서가 발송되었습니다",
        "report_id": report_id,
        "seq": seq,
        "recipients": to + cc,
        "sent_at": now,
    }
