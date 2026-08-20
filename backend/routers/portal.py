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
    Buyer,
    Client,
    Project,
    ProjectParticipationSnapshot,
    ProjectSale,
    ProjectVehicle,
    User,
    get_db,
)
from services.audit_logger import AuditLogger
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


@router.get("/me", response_model=schemas.PortalMe)
def get_me(user: User = Depends(_external), db: Session = Depends(get_db)):
    """로그인한 외부 사용자 신원(역할·소속) — /users/me는 외부역할 403이라 포털 전용 제공.

    org_name: PARTNER는 client_id→Client.company_name, INVESTOR는 buyer_id→Buyer.name.
    매핑 없거나 대상 없으면 None.
    """
    org_name = None
    if user.role == "PARTNER" and user.client_id:
        c = db.get(Client, user.client_id)
        if c is not None:
            org_name = c.company_name
    elif user.role == "INVESTOR" and user.buyer_id:
        b = db.get(Buyer, user.buyer_id)
        if b is not None:
            org_name = b.name
    return schemas.PortalMe(
        user_id=user.user_id, name=user.name, role=user.role, org_name=org_name
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
        AuditLogger.portal_view(db, user.user_id, project.project_id, user.role)
        db.commit()
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
    AuditLogger.portal_view(db, user.user_id, project.project_id, user.role)
    db.commit()
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


# ── P1 운수사(PARTNER) 확장 — 계약대수 현황·보고서 열람·정산 내역 (ACCESS_CONTROL_PLAN §3) ──
# 전부 read-only + 자기 client_id 스코프 강제. INVESTOR는 403(운수사 전용 데이터).
_partner = require_external_role("PARTNER")


def _require_client_id(user: User) -> str:
    if not user.client_id:
        raise HTTPException(status_code=403, detail="연결된 고객사가 없습니다")
    return user.client_id


@router.get("/fleet-status", response_model=List[schemas.FleetStatusTrendItem])
def portal_fleet_status(
    user: User = Depends(_partner),
    db: Session = Depends(get_db),
):
    """내 회사 계약대수 월별 추이 — 대수·차종 구성만(내부 분류·타사 데이터 미노출)."""
    from models import FleetStatus

    client_id = _require_client_id(user)
    rows = (
        db.query(FleetStatus)
        .filter(FleetStatus.client_id == client_id)
        .order_by(FleetStatus.period.desc())
        .all()
    )
    return [
        schemas.FleetStatusTrendItem(
            period=r.period, license_count=r.license_count, total_count=r.total_count,
            diesel=r.diesel, cng=r.cng, hybrid=r.hybrid, electric=r.electric,
            hydrogen=r.hydrogen, region=r.region, industry=r.industry,
        )
        for r in rows
    ]


# 발송 완료된 보고서만 노출(작성중·검토중 내부 상태 비노출)
_PORTAL_REPORT_STATUSES = ("SENT", "CONFIRMED")


@router.get("/reports", response_model=List[schemas.PortalReportItem])
def portal_reports(
    user: User = Depends(_partner),
    db: Session = Depends(get_db),
):
    """내 회사 월간 보고서 — 발송 완료분만(파일 있으면 다운로드 가능)."""
    from models import ReportDelivery

    client_id = _require_client_id(user)
    rows = (
        db.query(ReportDelivery)
        .filter(
            ReportDelivery.client_id == client_id,
            ReportDelivery.status.in_(_PORTAL_REPORT_STATUSES),
        )
        .order_by(ReportDelivery.period.desc())
        .all()
    )
    return [
        schemas.PortalReportItem(
            report_id=r.report_id, period=r.period, report_type=r.report_type,
            status=r.status, sent_at=r.sent_at,
            has_file=bool(r.pinned_doc_id or r.doc_id),
        )
        for r in rows
    ]


@router.get("/reports/{report_id}/download")
def portal_report_download(
    report_id: str,
    user: User = Depends(_partner),
    db: Session = Depends(get_db),
):
    """보고서 파일 다운로드 — 자기 회사 + 발송 완료분만. PORTAL 감사 로그."""
    from fastapi.responses import FileResponse, RedirectResponse

    from models import Document, ReportDelivery
    from services import storage

    client_id = _require_client_id(user)
    r = db.get(ReportDelivery, report_id)
    if r is None or r.client_id != client_id or r.status not in _PORTAL_REPORT_STATUSES:
        raise HTTPException(status_code=404, detail="보고서를 찾을 수 없습니다")
    doc_id = r.pinned_doc_id or r.doc_id
    doc = db.get(Document, doc_id) if doc_id else None
    if doc is None:
        raise HTTPException(status_code=404, detail="보고서 파일이 없습니다")
    try:
        url = storage.get_url(doc.file_url)
    except storage.StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if not url:
        raise HTTPException(status_code=404, detail="저장소에서 파일을 찾을 수 없습니다")
    AuditLogger.log_action(
        db, user.user_id, "PORTAL_REPORT_DOWNLOAD",
        target_type="REPORT", target_id=report_id, new_value=user.role,
    )
    db.commit()
    if url.startswith("http://") or url.startswith("https://"):
        return RedirectResponse(url)
    return FileResponse(url, filename=doc.title or "report")


@router.get("/settlements", response_model=List[schemas.PortalSettlementItem])
def portal_settlements(
    user: User = Depends(_partner),
    db: Session = Depends(get_db),
):
    """내 회사 정산 내역 — 확정 이후 헤더만(내부 스냅샷·타사 미노출)."""
    from models import Project, Settlement

    client_id = _require_client_id(user)
    rows = (
        db.query(Settlement, Project.project_name)
        .join(Project, Project.project_id == Settlement.project_id)
        .filter(Settlement.client_id == client_id)
        .order_by(Settlement.confirmed_at.desc())
        .all()
    )
    return [
        schemas.PortalSettlementItem(
            settlement_id=s.settlement_id, project_name=pname, period=s.period or None,
            status=s.status,
            confirmed_amount=float(s.confirmed_amount) if s.confirmed_amount is not None else None,
            vehicle_count=s.vehicle_count,
            confirmed_at=s.confirmed_at, completed_at=s.completed_at,
            paid_amount=float(s.paid_amount) if s.paid_amount is not None else None,
        )
        for s, pname in rows
    ]
