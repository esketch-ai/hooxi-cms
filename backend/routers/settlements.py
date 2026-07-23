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
from auth import get_current_user, require_permission, require_role
from models import (
    Project,
    ProjectClientMap,
    SettlementSnapshot,
    User,
    get_db,
    utcnow,
)
from routers import common
from services.audit_logger import AuditLogger

router = APIRouter(prefix="/settlements", tags=["settlements"])

# 정산 상태 전이 사전 — 역행·건너뛰기 금지 (SCR-07)
_TRANSITIONS = {"STANDBY": "BILLED", "BILLED": "COMPLETED"}


def _settlement_row(m: ProjectClientMap, project: Optional[Project],
                    client_name: Optional[str],
                    snapshot_count: int = 0) -> schemas.SettlementRow:
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
        snapshot_count=snapshot_count,
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
    # 회차 스냅샷 수 — 현재 페이지 map_id들만 그룹 집계(청구 취소 후 STANDBY도 이력 노출용)
    page_ids = [m.map_id for m in page_rows]
    snap_counts = (
        dict(
            db.query(SettlementSnapshot.map_id, func.count(SettlementSnapshot.seq))
            .filter(SettlementSnapshot.map_id.in_(page_ids))
            .group_by(SettlementSnapshot.map_id)
            .all()
        )
        if page_ids
        else {}
    )
    items = [
        _settlement_row(
            m, projects.get(m.project_id), cnames.get(m.client_id),
            snap_counts.get(m.map_id, 0),
        )
        for m in page_rows
    ]
    return schemas.SettlementListResponse(items=items, total=total)


@router.get("/{map_id}/snapshots", response_model=schemas.SettlementSnapshotListResponse)
def list_settlement_snapshots(
    map_id: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """정산 회차 스냅샷 조회 (R3-1) — 청구/입금 시점 동결 금액의 정본, seq 오름차순."""
    common.get_or_404(db, ProjectClientMap, map_id, "정산 대상")
    rows = (
        db.query(SettlementSnapshot)
        .filter(SettlementSnapshot.map_id == map_id)
        .order_by(SettlementSnapshot.seq.asc())
        .all()
    )
    unames = common.user_name_map(db, [s.created_by for s in rows])
    items = [
        schemas.SettlementSnapshotOut.model_validate(s, from_attributes=True).model_copy(
            update={"created_by_name": unames.get(s.created_by)}
        )
        for s in rows
    ]
    return schemas.SettlementSnapshotListResponse(items=items, total=len(items))


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
    - BILLED: 서버 계산 금액으로 확정 / COMPLETED: 직전 BILLED 스냅샷 금액 승계(재계산 금지)
    - tb_settlement_snapshot에 회차 동결(R3-1), tb_audit_log에 SETTLEMENT_CHANGE 기록
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

    now = utcnow()
    # 전이 시 함께 쓰는 필드를 UPDATE dict에 모아 원자 반영 (부수 필드 phantom 방지)
    values = {"settlement_status": target, "updated_at": now}
    if target == "BILLED":
        # 청구 시점 금액은 서버 계산 값으로 확정 (§10.3) — 이후 동결(스냅샷 정본)
        values["expected_amount"] = common.validate_expected_amount(
            common.compute_expected_amount(
                project.expected_credits, mapping.allocation_ratio,
                project.unit_price, mapping.success_fee_rate,
            )
        )
        values["billed_at"] = now
        values["billed_by"] = user.user_id
        # 발행 크레딧도 청구 시점 값으로 동결 (스냅샷 정본)
        issued_credits_snap = project.issued_credits
    else:  # COMPLETED — 재계산 금지: 직전 BILLED 스냅샷 금액 승계(청구·입금 회차 일치)
        billed_snap = (
            db.query(SettlementSnapshot)
            .filter(
                SettlementSnapshot.map_id == map_id,
                SettlementSnapshot.action == "BILLED",
            )
            .order_by(SettlementSnapshot.seq.desc())
            .first()
        )
        # BILLED 스냅샷이 없으면 현재 expected_amount 유지 (방어)
        values["expected_amount"] = (
            billed_snap.amount if billed_snap is not None else mapping.expected_amount
        )
        # amount와 동일하게 issued_credits도 BILLED 스냅샷에서 승계 — 동결 금액과 근거(발행
        # 크레딧)를 일치시킨다. BILLED~COMPLETED 사이 project.issued_credits 변동에 영향받지 않음.
        issued_credits_snap = (
            billed_snap.issued_credits if billed_snap is not None else project.issued_credits
        )
        values["completed_at"] = now
        values["completed_by"] = user.user_id
        if payload.paid_amount is not None:
            values["paid_amount"] = payload.paid_amount
        values["payment_type"] = payload.payment_type or mapping.payment_type or "FULL"

    # 조건부 UPDATE (낙관적 동시성, P0-B 준용) — 스냅샷 기준 커밋은 동시 전이 시
    # lost update + 실제 없던 전이가 스냅샷·감사에 기록되는 문제가 있어, 읽은 상태가
    # 그대로일 때만 갱신하고 rowcount 0이면 409로 반려한다.
    updated = (
        db.query(ProjectClientMap)
        .filter(
            ProjectClientMap.map_id == map_id,
            ProjectClientMap.settlement_status == mapping.settlement_status,
        )
        .update(values, synchronize_session=False)
    )
    if updated == 0:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="다른 사용자가 방금 정산 상태를 변경했습니다. 새로고침 후 다시 시도하세요",
        )

    # 회차 스냅샷 동결 (R3-1, append-only) — 실제 전이(rowcount 1)일 때만 적재
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
            issued_credits=issued_credits_snap,
            amount=values["expected_amount"],
            unit_price=project.unit_price,
            allocation_ratio=mapping.allocation_ratio,
            success_fee_rate=mapping.success_fee_rate,
            paid_amount=values.get("paid_amount", mapping.paid_amount),
            action=target,
            reason=payload.reason,
            created_by=user.user_id,
        )
    )
    # 감사 로그 (R2) — 금액·값 원문 기록 금지, 상태만. 실제 전이일 때만 적재
    AuditLogger.settlement_change(db, user.user_id, map_id, current, target)
    db.commit()
    db.refresh(mapping)  # 조건부 UPDATE(synchronize_session=False) 반영분으로 응답 직렬화
    cnames = common.client_name_map(db, [mapping.client_id])
    snap_count = (
        db.query(func.count(SettlementSnapshot.seq))
        .filter(SettlementSnapshot.map_id == map_id)
        .scalar()
        or 0
    )
    return _settlement_row(mapping, project, cnames.get(mapping.client_id), snap_count)


@router.post("/{map_id}/revert", response_model=schemas.SettlementRow)
def revert_settlement_billing(
    map_id: str,
    payload: schemas.SettlementRevert,
    user: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """청구 취소 (BILLED→STANDBY) — 오발행 정정. ADMIN 전용(§10.1).

    - 청구(BILLED) 상태에서만 취소 가능. STANDBY·COMPLETED(종단)는 409로 거절.
    - billed_at/by 초기화 후 STANDBY 복귀 — 금액은 재청구 시 서버 재계산(동결 해제).
    - REVERTED 스냅샷(append-only)에 취소 직전 청구 회차(금액·발행크레딧)를 담아 이력 보존.
    - 낙관적 동시성: 읽은 상태가 BILLED 그대로일 때만 갱신, 아니면 409.
    """
    mapping = common.get_or_404(db, ProjectClientMap, map_id, "정산 대상")
    project = common.get_or_404(db, Project, mapping.project_id, "감축 사업")

    current = mapping.settlement_status or "STANDBY"
    if current != "BILLED":
        raise HTTPException(
            status_code=409,
            detail="청구 취소는 청구(BILLED) 상태에서만 가능합니다 (현재 {0})".format(current),
        )

    now = utcnow()
    # 취소 이력 스냅샷은 취소 직전 청구 회차 값을 담는다 — 직전 BILLED 스냅샷(정본) 승계
    billed_snap = (
        db.query(SettlementSnapshot)
        .filter(SettlementSnapshot.map_id == map_id, SettlementSnapshot.action == "BILLED")
        .order_by(SettlementSnapshot.seq.desc())
        .first()
    )
    # 취소 이력은 직전 BILLED 스냅샷(동결 정본)을 그대로 복제 — 금액·크레딧뿐 아니라
    # 단가·배분율·보수율도 승계해 "새 배분율 + 옛 금액" 혼재를 막는다(정본성 보존).
    if billed_snap is not None:
        reverted_amount = billed_snap.amount
        reverted_credits = billed_snap.issued_credits
        reverted_unit_price = billed_snap.unit_price
        reverted_alloc = billed_snap.allocation_ratio
        reverted_fee = billed_snap.success_fee_rate
    else:
        reverted_amount = mapping.expected_amount
        reverted_credits = project.issued_credits
        reverted_unit_price = project.unit_price
        reverted_alloc = mapping.allocation_ratio
        reverted_fee = mapping.success_fee_rate

    values = {
        "settlement_status": "STANDBY",
        "billed_at": None,
        "billed_by": None,
        "updated_at": now,
    }
    updated = (
        db.query(ProjectClientMap)
        .filter(
            ProjectClientMap.map_id == map_id,
            ProjectClientMap.settlement_status == "BILLED",
        )
        .update(values, synchronize_session=False)
    )
    if updated == 0:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="다른 사용자가 방금 정산 상태를 변경했습니다. 새로고침 후 다시 시도하세요",
        )

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
            issued_credits=reverted_credits,
            amount=reverted_amount,
            unit_price=reverted_unit_price,
            allocation_ratio=reverted_alloc,
            success_fee_rate=reverted_fee,
            paid_amount=mapping.paid_amount,
            action="REVERTED",
            reason=payload.reason,
            created_by=user.user_id,
        )
    )
    AuditLogger.settlement_change(db, user.user_id, map_id, current, "STANDBY")
    db.commit()
    db.refresh(mapping)
    cnames = common.client_name_map(db, [mapping.client_id])
    snap_count = (
        db.query(func.count(SettlementSnapshot.seq))
        .filter(SettlementSnapshot.map_id == map_id)
        .scalar()
        or 0
    )
    return _settlement_row(mapping, project, cnames.get(mapping.client_id), snap_count)
