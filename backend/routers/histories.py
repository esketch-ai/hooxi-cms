"""활동 이력·이슈 — SCR-05 목록/등록 + SCR-02 칸반 상태 변경·코멘트 스레드 (P1)."""

from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_permission
from models import ActivityHistory, Client, IssueComment, User, get_db
from routers import common
from routers.codes import validate_active_code
from services.audit_logger import AuditLogger

router = APIRouter(prefix="/histories", tags=["histories"])


@router.get("", response_model=schemas.HistoryListResponse)
def list_histories(
    client_id: Optional[str] = Query(None, description="고객사"),
    activity_type: Optional[str] = Query(None, description="CALL/MEETING/SITE_VISIT/EMAIL/ISSUE/KAKAO"),
    created_by: Optional[str] = Query(None, description="작성자"),
    manager_id: Optional[str] = Query(None, description="담당자"),
    retention_stage: Optional[str] = Query(None, description="리텐션 단계"),
    issue_status: Optional[str] = Query(None, description="OPEN/IN_PROGRESS/HOLD/CLOSED"),
    priority: Optional[str] = Query(None, description="URGENT/NORMAL"),
    date_from: Optional[date] = Query(None, description="기간 시작"),
    date_to: Optional[date] = Query(None, description="기간 끝"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """활동 이력 목록 (SCR-05) — 고객사·유형·작성자·기간·리텐션 필터."""
    query = db.query(ActivityHistory)
    if client_id:
        query = query.filter(ActivityHistory.client_id == client_id)
    if activity_type:
        query = query.filter(ActivityHistory.activity_type == activity_type)
    if created_by:
        query = query.filter(ActivityHistory.created_by == created_by)
    if manager_id:
        query = query.filter(ActivityHistory.manager_id == manager_id)
    if retention_stage:
        query = query.filter(ActivityHistory.retention_stage == retention_stage)
    if issue_status:
        query = query.filter(ActivityHistory.issue_status == issue_status)
    if priority:
        query = query.filter(ActivityHistory.priority == priority)
    if date_from:
        query = query.filter(ActivityHistory.activity_date >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.filter(ActivityHistory.activity_date <= datetime.combine(date_to, datetime.max.time()))

    total = query.count()
    rows = (
        query.order_by(ActivityHistory.activity_date.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return schemas.HistoryListResponse(items=common.build_history_outs(db, rows), total=total)


@router.post("", response_model=schemas.HistoryOut, status_code=201)
def create_history(
    payload: schemas.HistoryCreate,
    user: User = Depends(require_permission("crm.read_write")),
    db: Session = Depends(get_db),
):
    """이력 등록 (공용 ActivityForm) — created_by는 불변 작성자(GAN A1)."""
    validate_active_code(db, "ACTIVITY_TYPE", payload.activity_type)
    if payload.client_id:
        common.get_or_404(db, Client, payload.client_id, "고객사")
    manager_id = payload.manager_id or user.user_id
    if payload.manager_id:
        common.get_or_404(db, User, payload.manager_id, "담당자")

    is_issue = payload.activity_type == "ISSUE"
    history = ActivityHistory(
        client_id=payload.client_id,
        manager_id=manager_id,
        created_by=user.user_id,
        activity_date=payload.activity_date,
        activity_type=payload.activity_type,
        retention_stage=payload.retention_stage,
        # 이슈 전용 필드 — ISSUE 외 유형에는 저장하지 않음 (결정 1호·GAN A2)
        issue_status=(payload.issue_status or "OPEN") if is_issue else None,
        priority=(payload.priority or "NORMAL") if is_issue else None,
        due_date=payload.due_date if is_issue else None,
        next_action=payload.next_action,
        title=payload.title,
        content=payload.content,
        main_needs=payload.main_needs,
    )
    db.add(history)
    db.commit()
    db.refresh(history)
    return common.build_history_outs(db, [history])[0]


@router.put("/{history_id}/status", response_model=schemas.HistoryOut)
def update_issue_status(
    history_id: str,
    payload: schemas.IssueStatusUpdate,
    user: User = Depends(require_permission("crm.read_write")),
    db: Session = Depends(get_db),
):
    """이슈 상태 변경 (SCR-02 칸반 드래그) — 변경 이력을 코멘트 스레드에 자동 적재(GAN A4)."""
    history = common.get_or_404(db, ActivityHistory, history_id, "활동 이력")
    if history.activity_type != "ISSUE":
        raise HTTPException(status_code=409, detail="이슈(ISSUE) 유형의 이력만 상태를 변경할 수 있습니다")

    old_status = history.issue_status or "-"
    if old_status != payload.issue_status:
        history.issue_status = payload.issue_status
        content = "상태 변경: {0} → {1}".format(old_status, payload.issue_status)
        if payload.comment:
            content += " — {0}".format(payload.comment)
        db.add(
            IssueComment(
                history_id=history.history_id,
                manager_id=user.user_id,
                comment_type="STATUS_CHANGE",
                content=content,
            )
        )
        AuditLogger.log_action(
            db, 
            user.user_id, 
            "ISSUE_STATUS_CHANGE",
            target_type="HISTORY", 
            target_id=history.history_id,
            old_value=old_status,
            new_value=payload.issue_status
        )
        db.commit()
        db.refresh(history)
    return common.build_history_outs(db, [history])[0]


@router.get("/{history_id}/comments", response_model=List[schemas.CommentOut])
def list_comments(
    history_id: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """이슈 카드 Drawer 코멘트 스레드 (tb_issue_comment) — 시간순."""
    common.get_or_404(db, ActivityHistory, history_id, "활동 이력")
    rows = (
        db.query(IssueComment)
        .filter(IssueComment.history_id == history_id)
        .order_by(IssueComment.created_at.asc())
        .all()
    )
    return common.build_comment_outs(db, rows)


@router.post("/{history_id}/comments", response_model=schemas.CommentOut, status_code=201)
def create_comment(
    history_id: str,
    payload: schemas.CommentCreate,
    user: User = Depends(require_permission("crm.read_write")),
    db: Session = Depends(get_db),
):
    """처리 코멘트 등록 — 부서원 누구나 기록 (SCR-02)."""
    common.get_or_404(db, ActivityHistory, history_id, "활동 이력")
    comment = IssueComment(
        history_id=history_id,
        manager_id=user.user_id,
        comment_type=payload.comment_type,
        content=payload.content,
    )
    db.add(comment)
    AuditLogger.log_action(
        db, 
        user.user_id, 
        "COMMENT_ADD",
        target_type="HISTORY_COMMENT", 
        target_id=history_id
    )
    db.commit()
    db.refresh(comment)
    return common.build_comment_outs(db, [comment])[0]
