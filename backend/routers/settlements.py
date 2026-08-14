"""정산 헤더 확정·상태전이 — SCR-07 (P4 정산 재건).

그레인 = (고객사 × 사업 [× 기간]). 예정은 lazy(header 없음), 최초 확정 시 tb_settlement 1건 생성.
상태머신: (예정) → 확정 CONFIRMED → 청구 BILLED → 입금완료 COMPLETED(종단). 청구취소 BILLED→CONFIRMED.

- 확정(freeze): confirmed_amount = Σ ProjectVehicle.expected_payout(확정 시점 동결). 이후 차량
  예상지급액이 바뀌어도 confirmed_amount는 불변(스냅샷 정본, R3-1 동결 불변식).
- 금액은 스냅샷에 동결(append-only), 감사 로그(SETTLEMENT_CHANGE)에는 상태 전이만 기록(R2-E6).
- 낙관적 동시성(P0-B 준용): 읽은 상태가 그대로일 때만 조건부 UPDATE, rowcount 0이면 409.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import schemas
from auth import ROLE_LEVEL, get_current_user, require_permission
from models import (
    Client,
    Project,
    ProjectVehicle,
    Settlement,
    SettlementSnapshot,
    User,
    get_db,
    utcnow,
)
from routers import common
from routers.codes import validate_active_code
from services import pipeline
from services.audit_logger import AuditLogger

router = APIRouter(prefix="/settlements", tags=["settlements"])

# 정산 상태 전이 사전 — 허용 전이만 명시(그 외 역행·건너뛰기·종단전이 409).
# BILLED→CONFIRMED(청구취소)는 ADMIN 전용으로 라우터에서 별도 게이트.
_TRANSITIONS = {
    "CONFIRMED": {"BILLED"},
    "BILLED": {"COMPLETED", "CONFIRMED"},
}

# 전이별 스냅샷/감사 action 라벨 — (현재, 목표) → action
_ACTION_OF = {
    ("CONFIRMED", "BILLED"): "BILLED",
    ("BILLED", "COMPLETED"): "COMPLETED",
    ("BILLED", "CONFIRMED"): "REVERTED",  # 청구취소
}


def _next_seq(db: Session, settlement_id: str) -> int:
    """스냅샷 회차 seq — append-only(max+1). map_id 컬럼에 settlement_id 보관(재활용 감사키)."""
    return (
        db.query(func.coalesce(func.max(SettlementSnapshot.seq), 0))
        .filter(SettlementSnapshot.map_id == settlement_id)
        .scalar()
        or 0
    ) + 1


@router.get("", response_model=schemas.SettlementListResponse)
def list_settlements(
    client_id: Optional[str] = Query(None, description="고객사"),
    project_id: Optional[str] = Query(None, description="사업"),
    status: Optional[str] = Query(None, description="SETTLEMENT_STATUS: CONFIRMED/BILLED/COMPLETED"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """정산 헤더 목록(내부 조회) — 확정 이후(header 존재)만 노출. 예정은 P2 요약(live)에서."""
    query = db.query(Settlement)
    if client_id:
        query = query.filter(Settlement.client_id == client_id)
    if project_id:
        query = query.filter(Settlement.project_id == project_id)
    if status:
        query = query.filter(Settlement.status == status)
    rows = query.order_by(Settlement.created_at.desc()).all()
    items = [schemas.SettlementOut.model_validate(s, from_attributes=True) for s in rows]
    return schemas.SettlementListResponse(items=items, total=len(items))


@router.get("/pipeline", response_model=schemas.PipelineResponse)
def settlement_pipeline_view(
    client_id: Optional[str] = Query(None, description="운수사(ProjectVehicle.client_id)"),
    project_id: Optional[str] = Query(None, description="사업"),
    settlement_status: Optional[str] = Query(
        None, description="SETTLEMENT_STATUS: CONFIRMED/BILLED/COMPLETED(파생 status 일치 행만)"
    ),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """부서 워크플로우 파이프라인(내부 전용) — (운수사×사업) 5단계 진행 현황판.

    수집→결산→정산→보고→통지 진행상태를 기존 데이터·정산 헤더에서 파생한다(신규 데이터 없음).
    OBSERVER는 /settlements* 관찰 스코프 미화이트리스트라 get_current_user에서 자동 403,
    외부역할도 자동 403(내부 전용). 파생·신호 강약은 services.pipeline 참조.
    """
    result = pipeline.settlement_pipeline(
        db,
        client_id=client_id,
        project_id=project_id,
        settlement_status=settlement_status,
    )
    return schemas.PipelineResponse(**result)


@router.get("/{settlement_id}/snapshots", response_model=schemas.SettlementSnapshotListResponse)
def list_settlement_snapshots(
    settlement_id: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """정산 회차 스냅샷 조회 (R3-1) — 확정/청구/입금/취소 시점 동결 금액의 정본, seq 오름차순."""
    common.get_or_404(db, Settlement, settlement_id, "정산")
    rows = (
        db.query(SettlementSnapshot)
        .filter(SettlementSnapshot.map_id == settlement_id)
        .order_by(SettlementSnapshot.seq.asc())
        .all()
    )
    items = [
        schemas.SettlementSnapshotOut.model_validate(s, from_attributes=True) for s in rows
    ]
    return schemas.SettlementSnapshotListResponse(items=items, total=len(items))


@router.post("/confirm", response_model=schemas.SettlementOut, status_code=201)
def confirm_settlement(
    payload: schemas.SettlementConfirmRequest,
    user: User = Depends(require_permission("settlement.change")),
    db: Session = Depends(get_db),
):
    """정산 확정(freeze) — 예정(header 없음)→확정 CONFIRMED. MANAGER 이상(§10.1).

    - confirmed_amount = Σ ProjectVehicle.expected_payout(client×project, 확정 시점) — 전건
      None(미산정)이면 409(확정 불가). vehicle_count·effective_reduction도 동결 스냅샷.
    - (고객사, 사업, 기간) 헤더가 이미 있으면 409(중복 확정). period 미지정은 '' sentinel로
      정규화·저장 — PG 유니크가 NULL을 distinct 취급해 NULL 중복을 못 막으므로(DB 백스톱).
    - Settlement insert + SettlementSnapshot(seq=1, action=CONFIRMED) append + 감사 SETTLEMENT_CHANGE.
    - 동결 불변식: 확정 후 ProjectVehicle.expected_payout이 바뀌어도 confirmed_amount 불변(스냅샷 정본).
    """
    # period 미지정을 '' sentinel로 정규화 — uq(client,project,'')가 모든 DB에서 중복을 강제.
    period = (payload.period or "").strip()
    if period:
        common.validate_period(period)
    common.get_or_404(db, Client, payload.client_id, "고객사")
    common.get_or_404(db, Project, payload.project_id, "감축 사업")

    # 중복 확정 차단 — (고객사, 사업, 기간) 단일 헤더 (UniqueConstraint와 이중 방어).
    # 정규화된 '' sentinel 기준 비교(NULL distinct 함정 회피).
    exists = (
        db.query(Settlement)
        .filter(
            Settlement.client_id == payload.client_id,
            Settlement.project_id == payload.project_id,
            Settlement.period == period,
        )
        .first()
    )
    if exists is not None:
        raise HTTPException(status_code=409, detail="이미 확정된 정산입니다 (중복 확정 불가)")

    # 확정 시점 참여 차량의 예상지급액·유효감축량을 동결 — expected_payout은 부록 L 파생값
    vehicles = (
        db.query(ProjectVehicle)
        .filter(
            ProjectVehicle.client_id == payload.client_id,
            ProjectVehicle.project_id == payload.project_id,
        )
        .all()
    )
    # confirmed_amount 기여 차량 = expected_payout non-null 차량. vehicle_count·effective_reduction도
    # 이 동일 집합 기준으로 동결해 grain 정합("확정액/차량수·유효감축량" 해석 일관).
    contributing = [v for v in vehicles if v.expected_payout is not None]
    # None 전파: 전건 None(미산정)이면 확정 불가. 산정된 건이 하나라도 있으면 non-null 합으로 확정.
    if not contributing:
        raise HTTPException(status_code=409, detail="예상지급액 미산정 — 확정 불가")
    confirmed_amount = sum(v.expected_payout for v in contributing)
    effectives = [
        v.effective_reduction for v in contributing if v.effective_reduction is not None
    ]
    effective_reduction = sum(effectives) if effectives else None
    vehicle_count = len(contributing)

    now = utcnow()
    settlement = Settlement(
        client_id=payload.client_id,
        project_id=payload.project_id,
        period=period,
        status="CONFIRMED",
        confirmed_amount=confirmed_amount,
        vehicle_count=vehicle_count,
        effective_reduction=effective_reduction,
        confirmed_at=now,
        confirmed_by=user.user_id,
    )
    db.add(settlement)
    db.flush()  # settlement_id 확보(스냅샷 map_id·감사 target_id)

    db.add(
        SettlementSnapshot(
            map_id=settlement.settlement_id,
            seq=1,
            amount=confirmed_amount,
            vehicle_count=vehicle_count,
            effective_reduction=effective_reduction,
            action="CONFIRMED",
            created_by=user.user_id,
        )
    )
    # 감사 — 상태 전이만(예정→CONFIRMED), 금액 원문 미기록(R2-E6)
    AuditLogger.settlement_change(
        db, user.user_id, settlement.settlement_id, "STANDBY", "CONFIRMED"
    )
    # 동시 확정 경합 — 앱 exists 검사를 통과한 두 요청이 동시에 insert하면 uq가 두번째를 거부.
    # IntegrityError를 409로 매핑(전이 엔드포인트의 낙관적 동시성 409와 대칭, 500 노출 방지).
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="이미 확정된 정산입니다")
    db.refresh(settlement)
    return schemas.SettlementOut.model_validate(settlement, from_attributes=True)


@router.put("/{settlement_id}/status", response_model=schemas.SettlementOut)
def update_settlement_status(
    settlement_id: str,
    payload: schemas.SettlementStatusUpdate,
    user: User = Depends(require_permission("settlement.change")),
    db: Session = Depends(get_db),
):
    """정산 상태 전이 (SCR-07) — CONFIRMED→BILLED→COMPLETED, 청구취소 BILLED→CONFIRMED(ADMIN).

    - MANAGER 이상(§10.1). 청구취소만 ADMIN 전용(그보다 좁게 — role ADMIN 아니면 403).
    - 허용 전이 외(역행·건너뛰기·COMPLETED 종단 전이)는 409.
    - 낙관적 동시성(P0-B): 읽은 상태 그대로일 때만 조건부 UPDATE, rowcount 0이면 409.
    - BILLED/COMPLETED/REVERTED 모두 confirmed_amount 승계(재계산 금지). 스냅샷 append-only 동결.
    """
    validate_active_code(db, "SETTLEMENT_STATUS", payload.target_status)
    settlement = common.get_or_404(db, Settlement, settlement_id, "정산")

    current = settlement.status
    target = payload.target_status
    if target not in _TRANSITIONS.get(current, set()):
        raise HTTPException(
            status_code=409,
            detail="정산 상태는 확정→청구→입금완료 순서로만 변경할 수 있습니다 "
                   "(현재 {0} → 요청 {1})".format(current, target),
        )

    action = _ACTION_OF[(current, target)]

    # 청구취소(BILLED→CONFIRMED)는 ADMIN 전용 + 사유 필수 — settlement.change보다 좁은 게이트
    if action == "REVERTED":
        if ROLE_LEVEL.get(user.role, 0) < ROLE_LEVEL.get("ADMIN", 99):
            raise HTTPException(status_code=403, detail="청구 취소는 ADMIN만 가능합니다")
        if not (payload.reason and payload.reason.strip()):
            raise HTTPException(status_code=400, detail="청구 취소 사유(reason)는 필수입니다")

    now = utcnow()
    # 전이 시 함께 쓰는 필드를 UPDATE dict에 모아 원자 반영(부수 필드 phantom 방지)
    values = {"status": target, "updated_at": now}
    if target == "BILLED":
        values["billed_at"] = now
        values["billed_by"] = user.user_id
    elif target == "COMPLETED":
        values["completed_at"] = now
        values["completed_by"] = user.user_id
        # 재계산 금지 — 확정 금액(confirmed_amount) 그대로 승계
        values["paid_amount"] = settlement.confirmed_amount
    else:  # REVERTED(청구취소) — 청구 흔적 클리어 후 CONFIRMED 복귀(금액 동결 유지)
        values["billed_at"] = None
        values["billed_by"] = None

    # 조건부 UPDATE(낙관적 동시성) — 읽은 status 그대로일 때만 갱신, 아니면 409로 반려.
    # (동시 전이 시 lost update + 실제 없던 전이가 스냅샷·감사에 기록되는 문제 방지)
    updated = (
        db.query(Settlement)
        .filter(Settlement.settlement_id == settlement_id, Settlement.status == current)
        .update(values, synchronize_session=False)
    )
    if updated == 0:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="다른 사용자가 방금 정산 상태를 변경했습니다. 새로고침 후 다시 시도하세요",
        )

    # 회차 스냅샷 동결(R3-1, append-only) — 실제 전이(rowcount 1)일 때만 적재.
    # 금액·지표는 확정 스냅샷값(settlement) 승계, 재계산 없음.
    db.add(
        SettlementSnapshot(
            map_id=settlement_id,
            seq=_next_seq(db, settlement_id),
            amount=settlement.confirmed_amount,
            paid_amount=(
                settlement.confirmed_amount if target == "COMPLETED" else settlement.paid_amount
            ),
            vehicle_count=settlement.vehicle_count,
            effective_reduction=settlement.effective_reduction,
            action=action,
            reason=payload.reason,
            created_by=user.user_id,
        )
    )
    # 감사 — 상태 전이만, 금액 원문 미기록(R2-E6)
    AuditLogger.settlement_change(db, user.user_id, settlement_id, current, target)
    db.commit()
    db.refresh(settlement)  # 조건부 UPDATE(synchronize_session=False) 반영분으로 직렬화
    return schemas.SettlementOut.model_validate(settlement, from_attributes=True)
