"""감축 사업 관리 — SCR-06 (P2).

- 목록: FilterBar(진행 상태·담당 PM·모니터링 주기) + 참여 고객사 수 + 예상 발급일(D-day용)
- 상세: 개요 + 참여 고객사 매핑(배분율·보수율 🔒·예상 정산액 🔒·정산 상태)
- 단가 수기 입력(§10.3, price_source=MANUAL) — 변경 시 매핑 expected_amount 재계산
  (청구 후 BILLED/COMPLETED 매핑은 금액 동결 — 스냅샷 정본, 재계산·수정·해제 불가)
- 배분율 합계 100% 초과 시 422 (서버 검증)
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_permission
from models import (
    Asset,
    Client,
    Code,
    Project,
    ProjectClientMap,
    ProjectStage,
    User,
    get_db,
)
from routers import common
from routers.codes import validate_active_code
from services.audit_logger import AuditLogger

router = APIRouter(prefix="/projects", tags=["projects"])

_PROJECT_FIELDS = [
    "client_id", "project_name", "reg_code", "project_status",
    "reg_date", "credit_start_date", "credit_end_date", "credit_period_type",
    "mon_start_date", "mon_end_date", "mon_cycle",
    "expected_issue_date", "expected_credits", "unit_price",
    "issued_credits", "issued_at", "manager_id",
]


def _project_status_codes(db: Session):
    """PROJECT_STATUS 활성 코드를 sort_order 순으로 — 단계 시드/정렬 소스(하드코딩 금지)."""
    rows = (
        db.query(Code)
        .filter(Code.category == "PROJECT_STATUS", Code.active == "Y")
        .all()
    )
    rows.sort(key=lambda r: (r.sort_order if r.sort_order is not None else 999, r.code))
    return [(r.code, r.sort_order) for r in rows]


def _seed_stages(db: Session, project: Project) -> None:
    """프로젝트 진행 단계 행을 PROJECT_STATUS 코드별로 보강(멱등). 커밋은 호출부 책임.

    신규 프로젝트·기존(레거시) 프로젝트 모두에서 누락 단계만 추가한다."""
    existing = {
        s.stage_code
        for s in db.query(ProjectStage).filter(
            ProjectStage.project_id == project.project_id
        )
    }
    for code, sort_order in _project_status_codes(db):
        if code not in existing:
            db.add(
                ProjectStage(
                    project_id=project.project_id,
                    stage_code=code,
                    sort_order=sort_order,
                )
            )


def _stage_outs(db: Session, project: Project):
    """진행 단계 목록(정렬) + 지연 단계 수. 지연 = 예정 경과 & 미도달(실제일 없음)."""
    today = date.today()
    rows = list(
        db.query(ProjectStage).filter(ProjectStage.project_id == project.project_id)
    )
    rows.sort(
        key=lambda s: (s.sort_order if s.sort_order is not None else 999, s.stage_code)
    )
    outs, delayed = [], 0
    for s in rows:
        is_delayed = bool(
            s.planned_date and s.actual_date is None and s.planned_date < today
        )
        if is_delayed:
            delayed += 1
        out = schemas.ProjectStageOut.model_validate(s, from_attributes=True)
        outs.append(out.model_copy(update={"delayed": is_delayed}))
    return outs, delayed


def _recalc_expected_amounts(db: Session, project: Project):
    """§10.3 — 사업 전체 매핑의 expected_amount를 서버 계산 값으로 재적재.

    청구 후(BILLED/COMPLETED) 매핑은 금액 동결 — 스냅샷(R3-1)이 정본이므로 건너뛴다.
    단가·발행량·매핑 변경 등 모든 재계산 경로에 공통 적용.
    """
    maps = (
        db.query(ProjectClientMap)
        .filter(ProjectClientMap.project_id == project.project_id)
        .all()
    )
    for m in maps:
        if (m.settlement_status or "STANDBY") != "STANDBY":
            continue  # 청구 후 금액 동결 — 스냅샷 정본
        # 상한 초과 시 422 — 초과를 유발한 단가·발행량 입력 자체를 차단 (#6 P2)
        m.expected_amount = common.validate_expected_amount(
            common.compute_expected_amount(
                project.expected_credits, m.allocation_ratio,
                project.unit_price, m.success_fee_rate,
            )
        )


def _validate_allocation_total(db: Session, project_id: str, new_ratio: float,
                               exclude_map_id: Optional[str] = None):
    """배분율 합계 100% 초과 시 422 — 합계 검증은 서버도 수행 (SCR-06)."""
    query = db.query(func.coalesce(func.sum(ProjectClientMap.allocation_ratio), 0)).filter(
        ProjectClientMap.project_id == project_id
    )
    if exclude_map_id:
        query = query.filter(ProjectClientMap.map_id != exclude_map_id)
    current_total = float(query.scalar() or 0)
    if current_total + float(new_ratio) > 100.0 + 1e-9:
        raise HTTPException(
            status_code=422,
            detail="배분율 합계가 100%를 초과합니다 (현재 {0:g}% + 신규 {1:g}%)".format(
                current_total, float(new_ratio)
            ),
        )


def _build_map_outs(db: Session, rows):
    cnames = common.client_name_map(db, [m.client_id for m in rows])
    asset_ids = {m.asset_id for m in rows if m.asset_id}
    assets = (
        db.query(Asset).filter(Asset.asset_id.in_(asset_ids)).all() if asset_ids else []
    )
    amap = {
        a.asset_id: " ".join(filter(None, [a.asset_group, a.asset_type, a.main_spec]))
        for a in assets
    }
    return [
        schemas.ProjectMapOut.model_validate(m, from_attributes=True).model_copy(
            update={
                "client_name": cnames.get(m.client_id),
                "asset_summary": amap.get(m.asset_id),
            }
        )
        for m in rows
    ]


def _project_detail(db: Session, project: Project) -> schemas.ProjectDetailOut:
    unames = common.user_name_map(db, [project.manager_id])
    maps = (
        db.query(ProjectClientMap)
        .filter(ProjectClientMap.project_id == project.project_id)
        .order_by(ProjectClientMap.created_at.asc())
        .all()
    )
    stages, delayed_count = _stage_outs(db, project)
    out = schemas.ProjectDetailOut.model_validate(project, from_attributes=True)
    return out.model_copy(
        update={
            "manager_name": unames.get(project.manager_id),
            "clients": _build_map_outs(db, maps),
            "allocation_total": round(
                sum(float(m.allocation_ratio or 0) for m in maps), 2
            ),
            "stages": stages,
            "delayed_stage_count": delayed_count,
        }
    )


@router.get("", response_model=schemas.ProjectListResponse)
def list_projects(
    project_status: Optional[str] = Query(None, description="기획/등록완료/모니터링/검증/발급완료"),
    manager_id: Optional[str] = Query(None, description="담당 PM"),
    mon_cycle: Optional[str] = Query(None, description="모니터링 주기"),
    search: Optional[str] = Query(None, description="사업명·고유번호 검색"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """사업 목록 (SCR-06) — 참여 고객사 수·예상 발급일(D-day 계산용) 포함."""
    query = db.query(Project)
    if project_status:
        query = query.filter(Project.project_status == project_status)
    if manager_id:
        query = query.filter(Project.manager_id == manager_id)
    if mon_cycle:
        query = query.filter(Project.mon_cycle == mon_cycle)
    if search:
        keyword = "%{0}%".format(common.escape_like(search.strip()))
        query = query.filter(
            Project.project_name.ilike(keyword, escape="\\")
            | Project.reg_code.ilike(keyword, escape="\\")
        )

    total = query.count()
    rows = (
        query.order_by(Project.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    ids = [p.project_id for p in rows]
    unames = common.user_name_map(db, [p.manager_id for p in rows])

    count_map = {}
    if ids:
        count_rows = (
            db.query(
                ProjectClientMap.project_id,
                func.count(func.distinct(ProjectClientMap.client_id)),
            )
            .filter(ProjectClientMap.project_id.in_(ids))
            .group_by(ProjectClientMap.project_id)
            .all()
        )
        count_map = {pid: cnt for pid, cnt in count_rows}

    # 지연 단계 수 — 목록 대상 프로젝트의 단계를 한 번에 조회해 파이썬에서 판정(N+1 회피)
    delay_map = {}
    if ids:
        today = date.today()
        for st in db.query(ProjectStage).filter(ProjectStage.project_id.in_(ids)):
            if st.planned_date and st.actual_date is None and st.planned_date < today:
                delay_map[st.project_id] = delay_map.get(st.project_id, 0) + 1

    items = [
        schemas.ProjectListItem.model_validate(p, from_attributes=True).model_copy(
            update={
                "manager_name": unames.get(p.manager_id),
                "client_count": count_map.get(p.project_id, 0),
                "delayed_stage_count": delay_map.get(p.project_id, 0),
            }
        )
        for p in rows
    ]
    return schemas.ProjectListResponse(items=items, total=total)


@router.get("/stage-delays", response_model=schemas.ProjectStageAlertsOut)
def project_stage_delays(
    imminent_days: int = Query(7, ge=1, le=60),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """진행 단계 지연/임박 관찰 (Phase 1 대시보드 위젯) — 경영전략실 대응용.

    지연 = 예정 경과 & 미도달, 임박 = 예정이 imminent_days 이내 & 미도달.
    (경로가 /{project_id}보다 먼저 등록되도록 목록 바로 뒤에 정의)
    """
    today = date.today()
    stages = (
        db.query(ProjectStage)
        .filter(ProjectStage.planned_date.isnot(None), ProjectStage.actual_date.is_(None))
        .all()
    )
    pnames = {
        p.project_id: p.project_name
        for p in db.query(Project.project_id, Project.project_name)
    }
    delayed, imminent = [], []
    for s in stages:
        name = pnames.get(s.project_id)
        if name is None:
            continue  # 삭제된 사업의 유령 단계 방어(정상 경로에선 자식 삭제로 발생 안 함)
        gap = (s.planned_date - today).days
        if gap < 0:
            delayed.append(
                schemas.ProjectStageAlert(
                    project_id=s.project_id,
                    project_name=name,
                    stage_code=s.stage_code,
                    planned_date=s.planned_date,
                    days=-gap,
                )
            )
        elif gap <= imminent_days:
            imminent.append(
                schemas.ProjectStageAlert(
                    project_id=s.project_id,
                    project_name=name,
                    stage_code=s.stage_code,
                    planned_date=s.planned_date,
                    days=gap,
                )
            )
    delayed.sort(key=lambda a: a.days, reverse=True)  # 오래 지연된 것부터
    imminent.sort(key=lambda a: a.days)  # 임박한 것부터
    return schemas.ProjectStageAlertsOut(delayed=delayed, imminent=imminent)


@router.post("", response_model=schemas.ProjectDetailOut, status_code=201)
def create_project(
    payload: schemas.ProjectCreate,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """사업 등록 (SCR-06) — 단가는 수기 입력(price_source=MANUAL, §10.3)."""
    validate_active_code(db, "PROJECT_STATUS", payload.project_status)
    if payload.client_id:
        common.get_or_404(db, Client, payload.client_id, "고객사")
    if payload.manager_id:
        common.get_or_404(db, User, payload.manager_id, "담당 PM")
    project = Project(
        **{f: getattr(payload, f) for f in _PROJECT_FIELDS}, price_source="MANUAL"
    )
    db.add(project)
    db.flush()  # PK(gen_uuid)는 flush 시점에 생성 — 감사 대상 ID 확보
    _seed_stages(db, project)  # 진행 단계 5행 자동 시드(Phase 1)
    AuditLogger.log_action(
        db,
        user.user_id,
        "PROJECT_CREATE",
        target_type="PROJECT",
        target_id=project.project_id,
    )
    db.commit()
    db.refresh(project)
    return _project_detail(db, project)


@router.get("/{project_id}", response_model=schemas.ProjectDetailOut)
def get_project(
    project_id: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """사업 상세 (SCR-06) — 개요 + 참여 고객사 매핑 목록 + 진행 단계."""
    project = common.get_or_404(db, Project, project_id, "감축 사업")
    _seed_stages(db, project)  # 레거시 프로젝트 단계 지연 보강(멱등)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # 동시 최초 시드 경합 — 이미 시드됨(uq_project_stage_slot)
    return _project_detail(db, project)


@router.put("/{project_id}", response_model=schemas.ProjectDetailOut)
def update_project(
    project_id: str,
    payload: schemas.ProjectUpdate,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """사업 수정 — 전달된 필드만 반영. 발행량·단가 변경 시 매핑 금액 재계산(§10.3)."""
    project = common.get_or_404(db, Project, project_id, "감축 사업")
    data = payload.model_dump(exclude_unset=True)
    if "project_status" in data:
        validate_active_code(db, "PROJECT_STATUS", data["project_status"])
    if data.get("client_id"):
        common.get_or_404(db, Client, data["client_id"], "고객사")
    if data.get("manager_id"):
        common.get_or_404(db, User, data["manager_id"], "담당 PM")
    old_price = project.unit_price  # 단가 감사(old→new)용 — setattr 전에 스냅샷
    old_status = project.project_status  # 실제 전이 판정용 — setattr 전에 스냅샷
    for field in _PROJECT_FIELDS:
        if field in data:
            setattr(project, field, data[field])
    if "unit_price" in data or "expected_credits" in data:
        _recalc_expected_amounts(db, project)
    # 진행 상태가 '실제로' 바뀔 때만 해당 단계의 실제 도달일 자동 기록(비어 있을 때만) — Phase 1.
    # (폼이 수정 시에도 project_status를 항상 재전송하므로, 값이 동일하면 도달일을 찍지 않아
    #  기존 지연 상태가 조용히 해제되는 것을 방지)
    if "project_status" in data and data["project_status"] != old_status:
        _seed_stages(db, project)
        db.flush()
        stage = (
            db.query(ProjectStage)
            .filter(
                ProjectStage.project_id == project.project_id,
                ProjectStage.stage_code == data["project_status"],
            )
            .first()
        )
        if stage is not None and stage.actual_date is None:
            stage.actual_date = date.today()

    # 일반 수정 경유 단가 변경도 전용 엔드포인트(update_unit_price)와 동일하게
    # price_source=MANUAL 설정 + PROJECT_UNIT_PRICE 감사(old→new) 적재 (§10.3, R2)
    new_price = data.get("unit_price")
    price_changed = "unit_price" in data and (
        (old_price is None) != (new_price is None)
        or (old_price is not None and float(old_price) != float(new_price))
    )
    if price_changed:
        project.price_source = "MANUAL"
        AuditLogger.log_action(
            db,
            user.user_id,
            "PROJECT_UNIT_PRICE",
            target_type="PROJECT",
            target_id=project.project_id,
            old_value="{0:g}".format(float(old_price)) if old_price is not None else None,
            new_value="{0:g}".format(float(new_price)) if new_price is not None else None,
        )

    # 감사 로그는 커밋 전에 적재해야 함께 저장된다 (커밋 후 add는 유실)
    AuditLogger.log_action(
        db,
        user.user_id,
        "PROJECT_UPDATE",
        target_type="PROJECT",
        target_id=project.project_id,
    )
    db.commit()
    db.refresh(project)
    return _project_detail(db, project)


@router.put("/{project_id}/stages", response_model=schemas.ProjectDetailOut)
def update_project_stages(
    project_id: str,
    payload: schemas.ProjectStagesUpdate,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """진행 단계 예정일/실제일 편집 (Phase 1) — 전달된 필드만 반영."""
    project = common.get_or_404(db, Project, project_id, "감축 사업")
    _seed_stages(db, project)
    db.flush()
    valid = {code for code, _ in _project_status_codes(db)}
    existing = {
        s.stage_code: s
        for s in db.query(ProjectStage).filter(
            ProjectStage.project_id == project_id
        )
    }
    for item in payload.stages:
        if item.stage_code not in valid:
            raise HTTPException(
                status_code=422,
                detail="유효한 진행 단계가 아닙니다: {0}".format(item.stage_code),
            )
        stage = existing.get(item.stage_code)
        if stage is None:
            continue
        fields_set = item.model_fields_set  # 전달된 필드만 갱신(부분 편집)
        if "planned_date" in fields_set:
            stage.planned_date = item.planned_date
        if "actual_date" in fields_set:
            stage.actual_date = item.actual_date
    AuditLogger.log_action(
        db,
        user.user_id,
        "PROJECT_STAGE_UPDATE",
        target_type="PROJECT",
        target_id=project_id,
    )
    db.commit()
    db.refresh(project)
    return _project_detail(db, project)


@router.delete("/{project_id}", response_model=schemas.MessageResponse)
def delete_project(
    project_id: str,
    user: User = Depends(require_permission("client.delete")),
    db: Session = Depends(get_db),
):
    """사업 삭제 — MANAGER 이상(§10.1). 정산이 진행된(BILLED/COMPLETED) 사업은 삭제 불가."""
    project = common.get_or_404(db, Project, project_id, "감축 사업")
    maps = (
        db.query(ProjectClientMap)
        .filter(ProjectClientMap.project_id == project_id)
        .all()
    )
    if any(m.settlement_status in ("BILLED", "COMPLETED") for m in maps):
        raise HTTPException(
            status_code=409, detail="정산이 진행된 사업은 삭제할 수 없습니다"
        )
    for m in maps:
        db.delete(m)
    # 진행 단계 자식 행 정리 — 없으면 Postgres FK 위반으로 삭제 실패(Phase 1)
    db.query(ProjectStage).filter(
        ProjectStage.project_id == project_id
    ).delete(synchronize_session=False)
    db.delete(project)

    AuditLogger.log_action(
        db,
        user.user_id,
        "PROJECT_DELETE",
        target_type="PROJECT", 
        target_id=project.project_id
    )
    
    db.commit()
    return schemas.MessageResponse(message="감축 사업이 삭제되었습니다")


@router.put("/{project_id}/unit-price", response_model=schemas.ProjectDetailOut)
def update_unit_price(
    project_id: str,
    payload: schemas.UnitPriceUpdate,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """배출권 단가 수기 입력 (§10.3, price_source=MANUAL).

    단가 변경 시 해당 사업 전체 매핑의 expected_amount를 재계산해 적재한다.
    null 전달 시 단가 미정 — 매핑 금액도 null(프론트 '미정').
    """
    project = common.get_or_404(db, Project, project_id, "감축 사업")
    old_price = project.unit_price
    project.unit_price = payload.unit_price
    project.price_source = "MANUAL"
    _recalc_expected_amounts(db, project)
    # 감사 로그 — 단가는 비밀값 아님(R2-E6 검토), 변경 추적 취지상 old→new 기록
    AuditLogger.log_action(
        db,
        user.user_id,
        "PROJECT_UNIT_PRICE",
        target_type="PROJECT",
        target_id=project.project_id,
        old_value="{0:g}".format(float(old_price)) if old_price is not None else None,
        new_value=(
            "{0:g}".format(float(payload.unit_price))
            if payload.unit_price is not None
            else None
        ),
    )
    db.commit()
    db.refresh(project)
    return _project_detail(db, project)


@router.post("/{project_id}/clients", response_model=schemas.ProjectMapOut, status_code=201)
def upsert_project_client(
    project_id: str,
    payload: schemas.ProjectMapIn,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """참여 고객사 매핑 등록/수정 (SCR-06) — 동일 고객사는 갱신(upsert).

    - 배분율 합계 100% 초과 시 422 (서버 검증)
    - expected_amount = 예상 발행량 × 배분율(%) × 단가 × 성공 보수율(%) — 서버 계산·적재.
      단가 미입력이면 null(프론트 '미정')
    - 연결 자산은 해당 고객사 소유여야 한다
    """
    # 사업 행을 잠가 같은 사업에 대한 동시 매핑 upsert를 직렬화 — 배분율 합계 검증의
    # read-validate-write TOCTOU로 합계가 100%를 넘는 과대 청구를 막는다(S2).
    # (SQLite 등 미지원 백엔드에선 무시되고, 운영 Postgres에서 실효)
    project = (
        db.query(Project)
        .filter(Project.project_id == project_id)
        .with_for_update()
        .first()
    )
    if project is None:
        raise HTTPException(status_code=404, detail="감축 사업을 찾을 수 없습니다")
    common.get_or_404(db, Client, payload.client_id, "고객사")
    if payload.asset_id:
        asset = common.get_or_404(db, Asset, payload.asset_id, "자산")
        if asset.client_id != payload.client_id:
            raise HTTPException(
                status_code=422, detail="연결 자산이 해당 고객사의 자산이 아닙니다"
            )

    existing = (
        db.query(ProjectClientMap)
        .filter(
            ProjectClientMap.project_id == project_id,
            ProjectClientMap.client_id == payload.client_id,
        )
        .first()
    )
    # 청구 후(BILLED/COMPLETED) 매핑은 배분율·보수율·자산 변경 불가 — 금액 동결 정합성
    if existing is not None and existing.settlement_status in ("BILLED", "COMPLETED"):
        raise HTTPException(
            status_code=409, detail="정산이 진행된 매핑은 수정할 수 없습니다"
        )
    _validate_allocation_total(
        db, project_id, payload.allocation_ratio,
        exclude_map_id=existing.map_id if existing else None,
    )

    old_ratio = existing.allocation_ratio if existing is not None else None
    if existing is None:
        existing = ProjectClientMap(
            project_id=project_id, client_id=payload.client_id,
            settlement_status="STANDBY",
        )
        db.add(existing)
    existing.asset_id = payload.asset_id
    existing.allocation_ratio = payload.allocation_ratio
    existing.success_fee_rate = payload.success_fee_rate
    existing.expected_amount = common.validate_expected_amount(
        common.compute_expected_amount(
            project.expected_credits, payload.allocation_ratio,
            project.unit_price, payload.success_fee_rate,
        )
    )
    try:
        db.flush()  # 신규 매핑 PK(gen_uuid)는 flush 시점 생성 — 감사 대상 ID 확보
    except IntegrityError:
        # 동시 등록 경합 — uq_project_client_map_slot 위반 (앱 검사의 DB 백스톱)
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="이미 등록된 매핑입니다 — 목록을 새로고침한 뒤 기존 매핑을 수정하세요",
        )
    # 감사 로그 — 배분율 요약만 기록(금액 원문 금지, R2-E6)
    AuditLogger.log_action(
        db,
        user.user_id,
        "PROJECT_MAP_UPSERT",
        target_type="PROJECT_CLIENT_MAP",
        target_id=existing.map_id,
        old_value="배분율 {0:g}%".format(float(old_ratio)) if old_ratio is not None else None,
        new_value="배분율 {0:g}%".format(float(payload.allocation_ratio)),
    )
    db.commit()
    db.refresh(existing)
    return _build_map_outs(db, [existing])[0]


@router.delete("/{project_id}/clients/{map_id}", response_model=schemas.MessageResponse)
def delete_project_client(
    project_id: str,
    map_id: str,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """참여 고객사 매핑 해제 — 정산이 진행된(BILLED/COMPLETED) 매핑은 해제 불가."""
    mapping = common.get_or_404(db, ProjectClientMap, map_id, "참여 고객사 매핑")
    if mapping.project_id != project_id:
        raise HTTPException(status_code=404, detail="해당 사업의 매핑이 아닙니다")
    if mapping.settlement_status in ("BILLED", "COMPLETED"):
        raise HTTPException(
            status_code=409, detail="정산이 진행된 매핑은 해제할 수 없습니다"
        )
    # 감사 로그 — 배분율 요약만 기록(금액 원문 금지, R2-E6)
    AuditLogger.log_action(
        db,
        user.user_id,
        "PROJECT_MAP_RELEASE",
        target_type="PROJECT_CLIENT_MAP",
        target_id=mapping.map_id,
        old_value=(
            "배분율 {0:g}%".format(float(mapping.allocation_ratio))
            if mapping.allocation_ratio is not None
            else None
        ),
    )
    db.delete(mapping)
    db.commit()
    return schemas.MessageResponse(message="참여 고객사 매핑이 해제되었습니다")
