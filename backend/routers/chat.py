"""카카오톡 상담 관제 — SCR-08 /chat (스레드·메시지·답변·모드 전환·뱃지).

- 답변: Event API 발송 시도(채널 친구 한정) — 성공 여부와 무관하게 STAFF 메시지 적재,
  발송 결과는 응답 delivery 필드(SENT/FAILED/NOT_CONFIGURED)로 전달.
- 종료(CLOSED 전환): 대화 요약을 tb_activity_history(KAKAO, [자동])로 적재.
- 폴링: GET messages?after=<message_id> 증분 조회(5초 폴링 대응).
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, tuple_
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user
from models import (
    ActivityHistory,
    ChatMessage,
    ChatThread,
    Client,
    KakaoContact,
    User,
    get_db,
    utcnow,
)
from routers import common
from services import integration_config, kakao_service

router = APIRouter(prefix="/chat", tags=["chat"])


def _event_name_staff_reply() -> str:
    """직원 답변 통지용 오픈빌더 이벤트 블록 이름 — 연동 설정(DB 우선 + env 폴백)."""
    return integration_config.resolve("KAKAO_EVENT_NAME") or "staff_reply"

# CLOSED 전환 시 활동 이력에 발췌할 최근 메시지 수
SUMMARY_MESSAGE_COUNT = 10

_SENDER_LABEL = {"CUSTOMER": "고객", "AI": "AI", "STAFF": "직원", "SYSTEM": "시스템"}


def _message_outs(db: Session, rows: List[ChatMessage]) -> List[schemas.ChatMessageOut]:
    unames = common.user_name_map(db, [m.sender_id for m in rows])
    return [
        schemas.ChatMessageOut.model_validate(m, from_attributes=True).model_copy(
            update={"sender_name": unames.get(m.sender_id)}
        )
        for m in rows
    ]


def _thread_out(db: Session, thread: ChatThread) -> schemas.ChatThreadOut:
    return _thread_outs(db, [thread])[0]


def _thread_outs(db: Session, rows: List[ChatThread]) -> List[schemas.ChatThreadOut]:
    cnames = common.client_name_map(db, [t.client_id for t in rows])
    unames = common.user_name_map(db, [t.assigned_manager_id for t in rows])

    contact_ids = {t.kakao_contact_id for t in rows if t.kakao_contact_id}
    contacts = (
        db.query(KakaoContact).filter(KakaoContact.contact_id.in_(contact_ids)).all()
        if contact_ids
        else []
    )
    cmap = {c.contact_id: c for c in contacts}

    # 미리보기 — 스레드별 마지막 메시지 1건
    previews = {}
    thread_ids = [t.thread_id for t in rows]
    if thread_ids:
        last_at = (
            db.query(
                ChatMessage.thread_id, func.max(ChatMessage.created_at).label("max_at")
            )
            .filter(ChatMessage.thread_id.in_(thread_ids))
            .group_by(ChatMessage.thread_id)
            .subquery()
        )
        last_rows = (
            db.query(ChatMessage)
            .join(
                last_at,
                (ChatMessage.thread_id == last_at.c.thread_id)
                & (ChatMessage.created_at == last_at.c.max_at),
            )
            .all()
        )
        for m in last_rows:
            previews[m.thread_id] = (m.content or "")[:80]

    outs = []
    for t in rows:
        contact = cmap.get(t.kakao_contact_id)
        out = schemas.ChatThreadOut.model_validate(t, from_attributes=True)
        outs.append(
            out.model_copy(
                update={
                    "client_name": cnames.get(t.client_id),
                    "contact_name": contact.name if contact else None,
                    "contact_phone": contact.phone if contact else None,
                    "assigned_manager_name": unames.get(t.assigned_manager_id),
                    "last_message_preview": previews.get(t.thread_id),
                }
            )
        )
    return outs


@router.get("/threads", response_model=schemas.ChatThreadListResponse)
def list_threads(
    search: Optional[str] = Query(None, description="고객사명·연락처 이름 검색"),
    status: Optional[str] = Query(None, description="OPEN/WAITING/CLOSED"),
    mode: Optional[str] = Query(None, description="AI/HUMAN"),
    client_id: Optional[str] = Query(None),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """스레드 리스트 — last_message_at 역순, 마지막 메시지 미리보기 포함."""
    query = db.query(ChatThread)
    if status:
        query = query.filter(ChatThread.status == status)
    if mode:
        query = query.filter(ChatThread.mode == mode)
    if client_id:
        query = query.filter(ChatThread.client_id == client_id)
    if search:
        term = "%{0}%".format(common.escape_like(search.strip()))
        query = (
            query.outerjoin(Client, Client.client_id == ChatThread.client_id)
            .outerjoin(KakaoContact, KakaoContact.contact_id == ChatThread.kakao_contact_id)
            .filter(
                or_(
                    Client.company_name.ilike(term, escape="\\"),
                    KakaoContact.name.ilike(term, escape="\\"),
                )
            )
        )

    rows = query.order_by(
        func.coalesce(ChatThread.last_message_at, ChatThread.created_at).desc()
    ).all()
    items = _thread_outs(db, rows)
    return schemas.ChatThreadListResponse(items=items, total=len(items))


@router.get("/badge", response_model=schemas.ChatBadgeResponse)
def chat_badge(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """LNB 뱃지 — 담당자 연결 대기(WAITING) 스레드 수."""
    waiting = db.query(ChatThread).filter(ChatThread.status == "WAITING").count()
    return schemas.ChatBadgeResponse(waiting=waiting)


@router.get("/threads/{thread_id}/messages", response_model=List[schemas.ChatMessageOut])
def list_messages(
    thread_id: str,
    after: Optional[str] = Query(None, description="증분 조회 기준 message_id"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """메시지 목록 — created_at 오름차순. after 지정 시 그 이후 증분만(폴링)."""
    common.get_or_404(db, ChatThread, thread_id, "상담 스레드")
    query = db.query(ChatMessage).filter(ChatMessage.thread_id == thread_id)
    if after:
        ref = db.get(ChatMessage, after)
        if ref is None or ref.thread_id != thread_id:
            raise HTTPException(status_code=404, detail="기준 메시지(after)를 찾을 수 없습니다")
        query = query.filter(
            tuple_(ChatMessage.created_at, ChatMessage.message_id)
            > (ref.created_at, ref.message_id)
        )
    rows = query.order_by(ChatMessage.created_at.asc(), ChatMessage.message_id.asc()).all()
    return _message_outs(db, rows)


@router.post("/threads/{thread_id}/reply", response_model=schemas.ChatReplyResponse)
def reply_thread(
    thread_id: str,
    payload: schemas.ChatReplyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """직원 답변 — Event API 발송 시도 + STAFF 메시지 적재(발송 실패해도 적재).

    delivery: SENT / FAILED / NOT_CONFIGURED — 프론트가 발송 결과를 표시.
    """
    thread = common.get_or_404(db, ChatThread, thread_id, "상담 스레드")
    contact = db.get(KakaoContact, thread.kakao_contact_id) if thread.kakao_contact_id else None

    delivery = "NOT_CONFIGURED"
    if kakao_service.is_configured_event():
        if contact is None:
            delivery = "FAILED"
        else:
            try:
                kakao_service.send_event(
                    kakao_user_key=contact.kakao_user_key,
                    event_name=_event_name_staff_reply(),
                    params={"content": payload.content},
                )
                delivery = "SENT"
            except Exception:
                delivery = "FAILED"  # 비친구 등 — 메시지는 적재하고 결과만 전달

    now = utcnow()
    message = ChatMessage(
        thread_id=thread.thread_id,
        sender_type="STAFF",
        sender_id=user.user_id,
        content=payload.content,
    )
    db.add(message)
    thread.mode = "HUMAN"
    thread.status = "OPEN"
    thread.last_message_at = now
    db.commit()
    db.refresh(message)
    return schemas.ChatReplyResponse(delivery=delivery, message=_message_outs(db, [message])[0])


@router.put("/threads/{thread_id}", response_model=schemas.ChatThreadOut)
def update_thread(
    thread_id: str,
    payload: schemas.ChatThreadUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """모드 전환(AI↔HUMAN)·담당 배정·상태 변경.

    CLOSED 전환 시 최근 메시지 발췌를 tb_activity_history(KAKAO, [자동])로 적재.
    """
    thread = common.get_or_404(db, ChatThread, thread_id, "상담 스레드")
    prev_status = thread.status

    if payload.assigned_manager_id is not None:
        common.get_or_404(db, User, payload.assigned_manager_id, "담당자")
        thread.assigned_manager_id = payload.assigned_manager_id
    if payload.mode is not None:
        thread.mode = payload.mode
    if payload.status is not None:
        thread.status = payload.status

    if payload.status == "CLOSED" and prev_status != "CLOSED":
        recent = (
            db.query(ChatMessage)
            .filter(ChatMessage.thread_id == thread.thread_id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.message_id.desc())
            .limit(SUMMARY_MESSAGE_COUNT)
            .all()
        )
        lines = [
            "[{0}] {1}".format(
                _SENDER_LABEL.get(m.sender_type, m.sender_type), (m.content or "")[:200]
            )
            for m in reversed(recent)
        ]
        client = db.get(Client, thread.client_id) if thread.client_id else None
        client_name = client.company_name if client else "미지정 고객"
        db.add(
            ActivityHistory(
                client_id=thread.client_id,
                manager_id=thread.assigned_manager_id or user.user_id,
                created_by=user.user_id,
                activity_date=utcnow(),
                activity_type="KAKAO",
                title="{0} 카카오 상담: {1}".format(common.AUTO_PREFIX, client_name),
                content="\n".join(lines) if lines else "대화 내용 없음",
            )
        )

    db.commit()
    db.refresh(thread)
    return _thread_out(db, thread)
