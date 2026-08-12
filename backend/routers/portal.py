"""포털 조회 엔드포인트 + 매직링크 인증 (Phase 4 INC-5 / 부록 N.8 D2).

외부계정(PARTNER/INVESTOR) 전용 경로. 내부 라우터·get_current_user는 절대 쓰지 않고
require_external_role만 게이트로 사용해 외부↔내부 격리(D3)를 지킨다. 응답 뷰는
services/portal.py 빌더를 재사용해 원가/매출 동시 노출을 원천 차단한다(빌더가 보장).

- POST /portal/auth/verify: 매직링크(magic) 토큰 → 자체 access+refresh 발급. 인증 불요
  (토큰 자체가 인증). ACTIVE·token_version 재검증 + 외부역할만 통과(내부역할 403).
- GET /portal/projects: 외부 사용자 스코프의 프로젝트 목록(최소 필드).
- GET /portal/projects/{project_id}: 스코프 검증 후 역할별 뷰(참여 없으면 404).
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import schemas
from auth import (
    EXTERNAL_ROLES,
    _verify_user_from_payload,
    create_access_token,
    create_refresh_token,
    decode_token,
    require_external_role,
)
from models import (
    Project,
    ProjectParticipationSnapshot,
    ProjectSale,
    ProjectVehicle,
    User,
    get_db,
)
from services.portal import build_investor_view, build_partner_view

router = APIRouter(prefix="/portal", tags=["portal"])

# 조회 엔드포인트 공통 게이트 — 외부역할만(내부역할·미인증 원천 차단)
_external = require_external_role("PARTNER", "INVESTOR")


@router.post("/auth/verify", response_model=schemas.TokenPair)
def verify_magic(payload: schemas.MagicVerifyIn, db: Session = Depends(get_db)):
    """매직링크 토큰 → access+refresh 교환. 만료/무효 토큰 401, 내부역할 403."""
    token_payload = decode_token(payload.token, "magic")  # 만료·무효·잘못된 유형 → 401
    user = _verify_user_from_payload(token_payload, db)    # ACTIVE·token_version 재검증
    if user.role not in EXTERNAL_ROLES:
        # 내부 계정의 magic 토큰은 포털 로그인 대상이 아님 — 격리(D3)
        raise HTTPException(status_code=403, detail="외부 포털 계정만 이용할 수 있습니다")
    return schemas.TokenPair(
        access_token=create_access_token(user),
        refresh_token=create_refresh_token(user),
    )


@router.get("/projects")
def list_projects(user: User = Depends(_external), db: Session = Depends(get_db)) -> List[dict]:
    """외부 사용자 스코프의 프로젝트 목록(project_id·project_name·project_status).

    PARTNER는 자기 client_id 참여 차량이 있는 프로젝트, INVESTOR는 자기 buyer_id
    거래계약이 있는 프로젝트만. client_id/buyer_id 미설정이면 빈 목록.
    """
    if user.role == "PARTNER":
        if not user.client_id:
            return []
        projects = (
            db.query(Project)
            .join(ProjectVehicle, ProjectVehicle.project_id == Project.project_id)
            .filter(ProjectVehicle.client_id == user.client_id)
            .distinct()
            .all()
        )
    else:  # INVESTOR
        if not user.buyer_id:
            return []
        projects = (
            db.query(Project)
            .join(ProjectSale, ProjectSale.project_id == Project.project_id)
            .filter(ProjectSale.buyer_id == user.buyer_id)
            .distinct()
            .all()
        )
    return [
        {
            "project_id": p.project_id,
            "project_name": p.project_name,
            "project_status": p.project_status,
        }
        for p in projects
    ]


@router.get("/projects/{project_id}")
def get_project(
    project_id: str,
    user: User = Depends(_external),
    db: Session = Depends(get_db),
):
    """스코프 검증 후 역할별 뷰 — 참여 없으면 404(존재 여부 노출 방지).

    응답은 PARTNER→PartnerPortalView, INVESTOR→InvestorPortalView (역할 union).
    """
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

    if user.role == "PARTNER":
        in_scope = user.client_id and (
            db.query(ProjectVehicle.vehicle_id)
            .filter(
                ProjectVehicle.project_id == project.project_id,
                ProjectVehicle.client_id == user.client_id,
            )
            .first()
        )
        if not in_scope:
            raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")
        return build_partner_view(db, project, user.client_id)

    # INVESTOR
    in_scope = user.buyer_id and (
        db.query(ProjectSale.sale_id)
        .filter(
            ProjectSale.project_id == project.project_id,
            ProjectSale.buyer_id == user.buyer_id,
        )
        .first()
    )
    if not in_scope:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")
    return build_investor_view(db, project, user.buyer_id)


@router.get("/projects/{project_id}/timeline")
def get_project_timeline(
    project_id: str,
    user: User = Depends(_external),
    db: Session = Depends(get_db),
) -> List[dict]:
    """변동 타임라인(ProjectParticipationSnapshot, captured_at asc) — 역할별 필드 게이팅.

    스코프 검증은 상세(get_project)와 동일 — 밖이면 404(존재 여부 비노출).
    - PARTNER: 자기 client_id 스냅샷만 → {captured_at, effective_reduction, expected_payout}.
      expected_payout None(산정 중)이면 그대로 노출.
    - INVESTOR: 프로젝트 전체(모든 client) 스냅샷 → {captured_at, effective_reduction}.
      expected_payout(원가)·client 식별정보는 응답에 원천 미포함(빌더가 아닌 여기서 보장).
    """
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

    query = db.query(ProjectParticipationSnapshot).filter(
        ProjectParticipationSnapshot.project_id == project.project_id
    )

    if user.role == "PARTNER":
        in_scope = user.client_id and (
            db.query(ProjectVehicle.vehicle_id)
            .filter(
                ProjectVehicle.project_id == project.project_id,
                ProjectVehicle.client_id == user.client_id,
            )
            .first()
        )
        if not in_scope:
            raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")
        rows = (
            query.filter(ProjectParticipationSnapshot.client_id == user.client_id)
            .order_by(ProjectParticipationSnapshot.captured_at.asc())
            .all()
        )
        return [
            {
                "captured_at": r.captured_at,
                "effective_reduction": (
                    round(float(r.effective_reduction_sum), 3)
                    if r.effective_reduction_sum is not None
                    else None
                ),
                "expected_payout": (
                    round(float(r.expected_payout_sum), 2)
                    if r.expected_payout_sum is not None
                    else None
                ),
            }
            for r in rows
        ]

    # INVESTOR — 프로젝트 전체 스냅샷, 감축량 시계열만(payout·client 식별 미포함)
    in_scope = user.buyer_id and (
        db.query(ProjectSale.sale_id)
        .filter(
            ProjectSale.project_id == project.project_id,
            ProjectSale.buyer_id == user.buyer_id,
        )
        .first()
    )
    if not in_scope:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")
    rows = query.order_by(ProjectParticipationSnapshot.captured_at.asc()).all()
    return [
        {
            "captured_at": r.captured_at,
            "effective_reduction": (
                round(float(r.effective_reduction_sum), 3)
                if r.effective_reduction_sum is not None
                else None
            ),
        }
        for r in rows
    ]
