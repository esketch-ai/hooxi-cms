"""카카오 채널 연동 — SCR-08 수신 파이프라인 + 연락처 승인 게이트(CR-3) + 수동 알림톡.

- POST /kakao/webhook: 오픈빌더 폴백 블록 스킬 서버(무인증 — ?secret= 쿼리 검증).
  5초 응답 제한 대응: 게이트 판정·메시지 적재·즉답만 수행(외부 호출 없음).
- GET/PUT /kakao/contacts: PENDING 승인(고객사 매핑 확정)·거절·차단 — MANAGER 이상.
- POST /comm/kakao/notify: 수동 알림톡 발송 — master.write.
"""

import json
import os
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_permission, require_role
from models import (
    ChatMessage,
    ChatThread,
    Client,
    Config,
    KakaoContact,
    User,
    get_db,
    utcnow,
)
from routers import common
from services.audit_logger import AuditLogger
from services import kakao_service

router = APIRouter(tags=["kakao"])

# 민감 키워드 기본값 — tb_config key "sensitive_keywords"(JSON 배열)로 재정의 가능
DEFAULT_SENSITIVE_KEYWORDS = ["수수료", "단가", "계약금액", "보수율", "정산액"]

# 담당자 연결(핸드오프) 트리거 발화 키워드
HANDOFF_KEYWORDS = ("상담", "담당자")


# ---------------------------------------------------------------------------
# 오픈빌더 스킬 응답 빌더 — v2.0 규격
# ---------------------------------------------------------------------------
def _skill_response(text: str, quick_replies: Optional[list] = None) -> dict:
    template = {"outputs": [{"simpleText": {"text": text}}]}
    if quick_replies:
        template["quickReplies"] = quick_replies
    return {"version": "2.0", "template": template}


def _handoff_quick_reply() -> list:
    return [{"label": "담당자 연결", "action": "message", "messageText": "담당자 연결"}]


def sensitive_keywords(db: Session) -> list:
    """tb_config sensitive_keywords(JSON 배열) — 미설정·파싱 실패 시 기본값."""
    row = db.get(Config, "sensitive_keywords")
    if row and row.config_value:
        try:
            parsed = json.loads(row.config_value)
            if isinstance(parsed, list):
                keywords = [str(k).strip() for k in parsed if str(k).strip()]
                if keywords:
                    return keywords
        except ValueError:
            pass
    return DEFAULT_SENSITIVE_KEYWORDS


# ---------------------------------------------------------------------------
# 웹훅 — 오픈빌더 폴백 블록 스킬 서버
# ---------------------------------------------------------------------------
@router.post("/kakao/webhook")
def kakao_webhook(
    payload: dict = Body(...),
    secret: Optional[str] = Query(None, description="KAKAO_WEBHOOK_SECRET 검증"),
    db: Session = Depends(get_db),
):
    """오픈빌더 스킬 요청 처리 — 게이트 판정 → 메시지 적재 → 즉답(5초 제한).

    - 미등록 kakao_user_key: PENDING 등록 + 확인 안내 (CR-3 보안 게이트)
    - PENDING/REJECTED/BLOCKED: 일반 안내만 (내부 정보 비노출)
    - APPROVED: 스레드 확보 → CUSTOMER 적재 → 민감 키워드 SYSTEM 적재
      → "상담"/"담당자" 발화 또는 clientExtra.action=handoff 시 WAITING 전환
    """
    expected = kakao_service.webhook_secret()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="카카오 웹훅이 설정되지 않았습니다. KAKAO_WEBHOOK_SECRET 환경변수를 설정하세요.",
        )
    if secret != expected:
        raise HTTPException(status_code=403, detail="웹훅 시크릿이 올바르지 않습니다")

    user_request = payload.get("userRequest") or {}
    kakao_user = (user_request.get("user") or {})
    kakao_user_key = kakao_user.get("id")
    if not kakao_user_key:
        raise HTTPException(status_code=422, detail="오픈빌더 요청에 사용자 키(userRequest.user.id)가 없습니다")
    utterance = (user_request.get("utterance") or "").strip()
    properties = kakao_user.get("properties") or {}
    client_extra = ((payload.get("action") or {}).get("clientExtra")) or {}

    contact = (
        db.query(KakaoContact).filter(KakaoContact.kakao_user_key == kakao_user_key).first()
    )

    # --- 미등록: PENDING 등록 + 안내 (CR-3) ---
    if contact is None:
        contact = KakaoContact(
            kakao_user_key=kakao_user_key,
            name=properties.get("nickname"),
            status="PENDING",
            requested_at=utcnow(),
            memo="첫 발화: {0}".format(utterance[:150]) if utterance else None,
        )
        db.add(contact)
        db.commit()
        return _skill_response(
            "안녕하세요, Hooxi Partners입니다.\n"
            "고객 확인 후 상담을 연결드리겠습니다. 소속 회사명과 성함을 남겨주시면 "
            "담당자가 빠르게 확인하겠습니다."
        )

    # --- 승인 전/거절/차단: 일반 안내만 ---
    if contact.status != "APPROVED":
        if contact.status == "PENDING":
            return _skill_response(
                "고객 확인이 진행 중입니다. 승인이 완료되면 상담을 도와드리겠습니다.\n"
                "잠시만 기다려 주세요."
            )
        return _skill_response(
            "안녕하세요, Hooxi Partners입니다.\n"
            "상담 이용이 어려운 계정입니다. 자세한 사항은 대표 번호로 문의해 주세요."
        )

    # --- APPROVED: 스레드 확보(OPEN, 없으면 생성) + CUSTOMER 적재 ---
    now = utcnow()
    thread = (
        db.query(ChatThread)
        .filter(
            ChatThread.kakao_contact_id == contact.contact_id,
            ChatThread.status != "CLOSED",
        )
        .order_by(ChatThread.created_at.desc())
        .first()
    )
    if thread is None:
        thread = ChatThread(
            client_id=contact.client_id,
            kakao_contact_id=contact.contact_id,
            mode="AI",
            status="OPEN",
        )
        db.add(thread)
        db.flush()

    db.add(ChatMessage(thread_id=thread.thread_id, sender_type="CUSTOMER", content=utterance))
    thread.last_message_at = now

    # 민감 키워드 검사 (tb_config) → SYSTEM 메시지 적재
    matched = [kw for kw in sensitive_keywords(db) if kw and kw in utterance]
    if matched:
        db.add(
            ChatMessage(
                thread_id=thread.thread_id,
                sender_type="SYSTEM",
                content="민감 키워드 감지: {0}".format(", ".join(matched)),
            )
        )

    # 담당자 연결(핸드오프) — 발화 키워드 또는 clientExtra.action=handoff
    handoff = (
        any(kw in utterance for kw in HANDOFF_KEYWORDS)
        or client_extra.get("action") == "handoff"
    )
    if handoff:
        thread.status = "WAITING"
        thread.mode = "HUMAN"
        db.commit()
        return _skill_response(
            "담당자 연결을 요청했습니다.\n"
            "확인 후 순차적으로 답변드리겠습니다. 잠시만 기다려 주세요."
        )

    db.commit()
    return _skill_response(
        "문의가 접수되었습니다.\n"
        "내용을 확인해 답변드리겠습니다. 담당자와 바로 상담을 원하시면 아래 버튼을 눌러주세요.",
        quick_replies=_handoff_quick_reply(),
    )


# ---------------------------------------------------------------------------
# 연락처 승인 게이트 (CR-3)
# ---------------------------------------------------------------------------
def _contact_out(db: Session, contact: KakaoContact) -> schemas.KakaoContactOut:
    cnames = common.client_name_map(db, [contact.client_id])
    unames = common.user_name_map(db, [contact.approved_by])
    out = schemas.KakaoContactOut.model_validate(contact, from_attributes=True)
    return out.model_copy(
        update={
            "client_name": cnames.get(contact.client_id),
            "approved_by_name": unames.get(contact.approved_by),
        }
    )


@router.get("/kakao/contacts", response_model=schemas.KakaoContactListResponse)
def list_kakao_contacts(
    status: Optional[str] = Query(None, description="PENDING/APPROVED/REJECTED/BLOCKED"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """연락처 목록 — 승인 대기 탭·승인 현황."""
    query = db.query(KakaoContact)
    if status:
        query = query.filter(KakaoContact.status == status)
    rows = query.order_by(KakaoContact.requested_at.desc()).all()

    cnames = common.client_name_map(db, [c.client_id for c in rows])
    unames = common.user_name_map(db, [c.approved_by for c in rows])
    items = [
        schemas.KakaoContactOut.model_validate(c, from_attributes=True).model_copy(
            update={
                "client_name": cnames.get(c.client_id),
                "approved_by_name": unames.get(c.approved_by),
            }
        )
        for c in rows
    ]
    return schemas.KakaoContactListResponse(items=items, total=len(items))


@router.put("/kakao/contacts/{contact_id}", response_model=schemas.KakaoContactOut)
def update_kakao_contact(
    contact_id: str,
    payload: schemas.KakaoContactUpdate,
    user: User = Depends(require_role("MANAGER")),
    db: Session = Depends(get_db),
):
    """승인(고객사 매핑 확정)·거절·차단 — MANAGER 이상 + 감사 로그(KAKAO_APPROVAL)."""
    contact = common.get_or_404(db, KakaoContact, contact_id, "카카오 연락처")
    old_status = contact.status

    if payload.status == "APPROVED":
        client_id = payload.client_id or contact.client_id
        if not client_id:
            raise HTTPException(
                status_code=422, detail="승인에는 고객사 매핑(client_id)이 필요합니다 (CR-3)"
            )
        common.get_or_404(db, Client, client_id, "고객사")
        contact.client_id = client_id
        contact.approved_by = user.user_id
        contact.approved_at = utcnow()
    elif payload.client_id:
        common.get_or_404(db, Client, payload.client_id, "고객사")
        contact.client_id = payload.client_id

    contact.status = payload.status
    if payload.name is not None:
        contact.name = payload.name
    if payload.phone is not None:
        contact.phone = payload.phone
    if payload.contact_role is not None:
        contact.contact_role = payload.contact_role
    if payload.memo is not None:
        contact.memo = payload.memo

    AuditLogger.kakao_approval(db, user.user_id, contact.contact_id, old_status, payload.status)
    db.commit()
    db.refresh(contact)
    return _contact_out(db, contact)


# ---------------------------------------------------------------------------
# 수동 알림톡 발송 (SCR-12 §5)
# ---------------------------------------------------------------------------
@router.post("/comm/kakao/notify", response_model=schemas.MessageResponse)
def send_kakao_notify(
    payload: schemas.KakaoNotifyRequest,
    _: User = Depends(require_permission("master.write")),
):
    """수동 알림톡 발송 — 미설정 503 / 발송 실패 502."""
    if not kakao_service.is_configured_alimtalk():
        raise HTTPException(
            status_code=503,
            detail=(
                "카카오 알림톡 발송 기능이 아직 설정되지 않았습니다. "
                "SOLAPI_API_KEY / SOLAPI_API_SECRET / KAKAO_PF_ID 환경변수를 설정한 뒤 다시 시도하세요."
            ),
        )
    template_code = payload.template_code or os.getenv("KAKAO_TEMPLATE_REPLY")
    if not template_code:
        raise HTTPException(
            status_code=422,
            detail="알림톡 템플릿이 지정되지 않았습니다. template_code 또는 KAKAO_TEMPLATE_REPLY를 설정하세요.",
        )
    try:
        kakao_service.send_alimtalk(
            to=payload.to,
            template_code=template_code,
            variables=payload.variables,
            buttons=payload.buttons,
        )
    except kakao_service.KakaoConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail="알림톡 발송에 실패했습니다: {0}".format(exc))
    return schemas.MessageResponse(message="알림톡이 발송되었습니다")
