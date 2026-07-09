"""고객사별 정산 현황 — SCR-07 (P2).

- tb_project_client_map 기반 목록: 고객사·사업명·지분율·보수율 🔒·예상 정산액 🔒·정산 상태
- 상태 전이: STANDBY→BILLED→COMPLETED (역행 금지 409) — MANAGER 이상(§10.1)
- 금액은 항상 서버 계산 값 사용(§10.3), 전이 시 tb_settlement_snapshot 동결(R3-1)
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_permission
from models import (
    AuditLog,
    Project,
    ProjectClientMap,
    SettlementSnapshot,
    User,
    get_db,
    utcnow,
)
from routers import common

router = APIRouter(prefix="/settlements", tags=["settlements"])

# 정산 상태 전이 사전 — 역행·건너뛰기 금지 (SCR-07)
_TRANSITIONS = {"STANDBY": "BILLED", "BILLED": "COMPLETED"}


def _settlement_row(m: ProjectClientMap, project: Optional[Project],
                    client_name: Optional[str]) -> schemas.SettlementRow:
    return schemas.SettlementRow(
        map_id=m.map_id,
        project_id=m.project_id,
        project_name=project.project_name if project else None,
        client_id=m.client_id,
        client_name=client_name,
        allocation_ratio=float(m.allocation_ratio) if m.allocation_ratio is not None else None,
        success_fee_rate=float(m.success_fee_rate) if m.success_fee_rate is not None else None,
        expected_amount=float(m.expected_amount) if m.expected_amount is not None else None,
        settlement_status=m.settlement_status or "STANDBY",
        unit_price=float(project.unit_price) if project and project.unit_price is not None else None,
        expected_credits=(
            float(project.expected_credits)
            if project and project.expected_credits is not None
            else None
        ),
        billed_at=m.billed_at,
        completed_at=m.completed_at,
        paid_amount=float(m.paid_amount) if m.paid_amount is not None else None,
        payment_type=m.payment_type,
    )


def _period_of(m: ProjectClientMap, project: Optional[Project]) -> Optional[str]:
    """정산 기준월 — 청구 시각(billed_at) 우선, 미청구(STANDBY)는 예상 발급월."""
    if m.billed_at:
        return m.billed_at.strftime("%Y-%m")
    if project and project.expected_issue_date:
        return project.expected_issue_date.strftime("%Y-%m")
    return None


@router.get("", response_model=schemas.SettlementListResponse)
def list_settlements(
    settlement_status: Optional[str] = Query(None, description="STANDBY/BILLED/COMPLETED"),
    project_id: Optional[str] = Query(None, description="사업"),
    period: Optional[str] = Query(None, description="정산 기준월 YYYY-MM"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """정산 목록 (SCR-07) — tb_project_client_map 기반. 금액은 서버 계산 값."""
    if period:
        common.validate_period(period)

    query = db.query(ProjectClientMap)
    if settlement_status:
        query = query.filter(ProjectClientMap.settlement_status == settlement_status)
    if project_id:
        query = query.filter(ProjectClientMap.project_id == project_id)
    rows = query.order_by(ProjectClientMap.created_at.asc()).all()

    projects = {
        p.project_id: p
        for p in db.query(Project)
        .filter(Project.project_id.in_({m.project_id for m in rows}))
        .all()
    } if rows else {}
    cnames = common.client_name_map(db, [m.client_id for m in rows])

    if period:
        rows = [m for m in rows if _period_of(m, projects.get(m.project_id)) == period]

    total = len(rows)
    page_rows = rows[(page - 1) * page_size:(page - 1) * page_size + page_size]
    items = [
        _settlement_row(m, projects.get(m.project_id), cnames.get(m.client_id))
        for m in page_rows
    ]
    return schemas.SettlementListResponse(items=items, total=total)


@router.put("/{map_id}/status", response_model=schemas.SettlementRow)
def update_settlement_status(
    map_id: str,
    payload: schemas.SettlementStatusUpdate,
    user: User = Depends(require_permission("settlement.change")),
    db: Session = Depends(get_db),
):
    """정산 상태 전이 (SCR-07) — STANDBY→BILLED→COMPLETED, 역행 금지 409.

    - MANAGER 이상만 가능(§10.1) — STAFF 403
    - 전이 시각·처리자 기록(billed_at/by·completed_at/by)
    - 금액은 서버 재계산 값으로 적재, tb_settlement_snapshot에 회차 동결(R3-1)
    - tb_audit_log에 SETTLEMENT_CHANGE 기록
    """
    mapping = common.get_or_404(db, ProjectClientMap, map_id, "정산 대상")
    project = common.get_or_404(db, Project, mapping.project_id, "감축 사업")

    current = mapping.settlement_status or "STANDBY"
    target = payload.settlement_status
    if _TRANSITIONS.get(current) != target:
        raise HTTPException(
            status_code=409,
            detail="정산 상태는 STANDBY→BILLED→COMPLETED 순서로만 변경할 수 있습니다 "
                   "(현재 {0} → 요청 {1})".format(current, target),
        )

    # 금액은 항상 서버 계산 값 사용 (§10.3)
    mapping.expected_amount = common.compute_expected_amount(
        project.expected_credits, mapping.allocation_ratio,
        project.unit_price, mapping.success_fee_rate,
    )

    now = utcnow()
    mapping.settlement_status = target
    if target == "BILLED":
        mapping.billed_at = now
        mapping.billed_by = user.user_id
    else:  # COMPLETED
        mapping.completed_at = now
        mapping.completed_by = user.user_id
        if payload.paid_amount is not None:
            mapping.paid_amount = payload.paid_amount
        mapping.payment_type = payload.payment_type or mapping.payment_type or "FULL"

    # 회차 스냅샷 동결 (R3-1, append-only)
    next_seq = (
        db.query(func.coalesce(func.max(SettlementSnapshot.seq), 0))
        .filter(SettlementSnapshot.map_id == map_id)
        .scalar()
        or 0
    ) + 1
    db.add(
        SettlementSnapshot(
            map_id=map_id,
            seq=next_seq,
            issued_credits=project.issued_credits,
            amount=mapping.expected_amount,
            unit_price=project.unit_price,
            allocation_ratio=mapping.allocation_ratio,
            success_fee_rate=mapping.success_fee_rate,
            paid_amount=mapping.paid_amount,
            action=target,
            reason=payload.reason,
            created_by=user.user_id,
        )
    )
    # 감사 로그 (R2) — 금액·값 원문 기록 금지, 상태만
    db.add(
        AuditLog(
            actor_id=user.user_id,
            action="SETTLEMENT_CHANGE",
            target_type="PROJECT_CLIENT_MAP",
            target_id=map_id,
            old_value=current,
            new_value=target,
        )
    )
    db.commit()
    db.refresh(mapping)
    cnames = common.client_name_map(db, [mapping.client_id])
    return _settlement_row(mapping, project, cnames.get(mapping.client_id))
