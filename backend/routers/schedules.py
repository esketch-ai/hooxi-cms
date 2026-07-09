"""일정 캘린더 — SCR-11 (P1).

- 월간/기간 조회 + 담당자·유형 필터
- 일자 드래그 변경(PUT start_at/end_at)
- 완료 처리: PLANNED → DONE 전환 시 tb_activity_history 자동 적재("[자동]" 표식)
"""

from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_permission
from models import ActivityHistory, Client, Schedule, User, get_db, utcnow
from routers import common

router = APIRouter(prefix="/schedules", tags=["schedules"])

# 일정 유형 → 활동 이력 유형 매핑 (완료 자동 적재 대상 — 고객 접점 유형만)
_ACTIVITY_TYPE_BY_SCHEDULE = {
    "MEETING": "MEETING",
    "CALL": "CALL",
    "SITE_VISIT": "SITE_VISIT",
}

_SCHEDULE_FIELDS = [
    "client_id", "manager_id", "schedule_type", "title",
    "start_at", "end_at", "location", "memo",
]


@router.get("", response_model=List[schemas.ScheduleOut])
def list_schedules(
    month: Optional[str] = Query(None, description="YYYY-MM (기간 필터와 택일)"),
    date_from: Optional[date] = Query(None, description="기간 시작"),
    date_to: Optional[date] = Query(None, description="기간 끝"),
    manager_id: Optional[str] = Query(None, description="담당자"),
    schedule_type: Optional[str] = Query(None, description="MEETING/CALL/SITE_VISIT/REPORT_DUE/INTERNAL"),
    client_id: Optional[str] = Query(None, description="고객사"),
    status: Optional[str] = Query(None, description="PLANNED/DONE/CANCELED"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """일정 목록 — month=YYYY-MM 또는 date_from/date_to 기간 필터."""
    query = db.query(Schedule)

    start = end = None
    if month:
        common.validate_period(month)
        start, end = common.period_bounds(month)
    else:
        if date_from:
            start = datetime.combine(date_from, datetime.min.time())
        if date_to:
            end = datetime.combine(date_to, datetime.max.time())
    if start is not None:
        # 기간과 겹치는 일정 포함 (end_at 없는 일정은 start_at 기준)
        query = query.filter(or_(Schedule.end_at >= start, Schedule.start_at >= start))
    if end is not None:
        query = query.filter(Schedule.start_at <= end)

    if manager_id:
        query = query.filter(Schedule.manager_id == manager_id)
    if schedule_type:
        query = query.filter(Schedule.schedule_type == schedule_type)
    if client_id:
        query = query.filter(Schedule.client_id == client_id)
    if status:
        query = query.filter(Schedule.status == status)

    rows = query.order_by(Schedule.start_at.asc()).all()
    return common.build_schedule_outs(db, rows)


@router.post("", response_model=schemas.ScheduleOut, status_code=201)
def create_schedule(
    payload: schemas.ScheduleCreate,
    user: User = Depends(require_permission("crm.read_write")),
    db: Session = Depends(get_db),
):
    """일정 등록 — manager 미지정 시 현재 사용자."""
    if payload.client_id:
        common.get_or_404(db, Client, payload.client_id, "고객사")
    if payload.manager_id:
        common.get_or_404(db, User, payload.manager_id, "담당자")

    schedule = Schedule(
        client_id=payload.client_id,
        manager_id=payload.manager_id or user.user_id,
        schedule_type=payload.schedule_type,
        title=payload.title,
        start_at=payload.start_at,
        end_at=payload.end_at,
        location=payload.location,
        memo=payload.memo,
        status="PLANNED",
        recur_rule=payload.recur_rule,
        recur_until=payload.recur_until,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return common.build_schedule_outs(db, [schedule])[0]


@router.put("/{schedule_id}", response_model=schemas.ScheduleOut)
def update_schedule(
    schedule_id: str,
    payload: schemas.ScheduleUpdate,
    user: User = Depends(require_permission("crm.read_write")),
    db: Session = Depends(get_db),
):
    """일정 수정 — 일자 드래그 변경·완료 처리.

    status가 DONE으로 전환되면 tb_activity_history에 "[자동]" 표식 이력을 적재하고
    schedule.history_id로 연결한다 (고객 접점 유형 MEETING/CALL/SITE_VISIT 대상).
    """
    schedule = common.get_or_404(db, Schedule, schedule_id, "일정")
    data = payload.model_dump(exclude_unset=True)

    if data.get("client_id"):
        common.get_or_404(db, Client, data["client_id"], "고객사")
    if data.get("manager_id"):
        common.get_or_404(db, User, data["manager_id"], "담당자")

    for field in _SCHEDULE_FIELDS:
        if field in data:
            setattr(schedule, field, data[field])

    new_status = data.get("status")
    became_done = new_status == "DONE" and schedule.status != "DONE"
    if new_status:
        schedule.status = new_status

    if became_done and schedule.history_id is None:
        activity_type = _ACTIVITY_TYPE_BY_SCHEDULE.get(schedule.schedule_type)
        if activity_type:
            history = ActivityHistory(
                client_id=schedule.client_id,
                manager_id=schedule.manager_id,
                created_by=user.user_id,
                activity_date=schedule.start_at or utcnow(),
                activity_type=activity_type,
                title="{0} 일정 완료: {1}".format(common.AUTO_PREFIX, schedule.title),
                content=payload.result_note or "일정 완료 처리로 자동 기록되었습니다.",
            )
            db.add(history)
            db.flush()
            schedule.history_id = history.history_id

    db.commit()
    db.refresh(schedule)
    return common.build_schedule_outs(db, [schedule])[0]
