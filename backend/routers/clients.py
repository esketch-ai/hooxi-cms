"""고객사 마스터 — SCR-03 목록/등록·SCR-03D 360° 뷰 (P1).

- 목록: FilterBar(구분·계약 상태·담당 PM·검색) + 최근 활동 일시 + 이번 달 보고서 상태 미니 배지
- 상세: 개요(구독 설정 포함) + 서브리소스(활동 이력/보고서/문서/자산)
- 민감 필드(success_fee_rate)는 응답에 포함하되 프론트가 마스킹 (reveal 감사 로그는 P2)
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_permission
from models import (
    ActivityHistory,
    Asset,
    Client,
    Document,
    ProjectClientMap,
    ReportDelivery,
    ReportSubscription,
    User,
    get_db,
)
from routers import common

router = APIRouter(prefix="/clients", tags=["clients"])

_CLIENT_FIELDS = [
    "client_type", "company_name", "biz_reg_no", "region", "address",
    "ceo_name", "ceo_contact_phone", "ceo_contact_email",
    "main_contact_name", "main_contact_phone", "main_contact_email",
    "contract_status", "contract_date", "keyman", "manager_id",
    "report_yn", "lat", "lng",
]


def _upsert_subscription(db: Session, client: Client, sub_in: schemas.ReportSubscriptionIn):
    """월간 보고서 설정 upsert — UNIQUE(client_id, report_type)."""
    sub = (
        db.query(ReportSubscription)
        .filter(
            ReportSubscription.client_id == client.client_id,
            ReportSubscription.report_type == sub_in.report_type,
        )
        .first()
    )
    if sub is None:
        sub = ReportSubscription(client_id=client.client_id, report_type=sub_in.report_type)
        db.add(sub)
    sub.channel = sub_in.channel
    sub.due_day = sub_in.due_day
    sub.active = sub_in.active
    # 활성 구독 등록 시 발송 대상 플래그 자동 설정 — report_yn 기본 N이라
    # 구독만 등록하고 generate 대상에서 빠지는 실수 방지 (QA 관찰 4)
    if sub_in.active == "Y":
        client.report_yn = "Y"


def _client_detail(db: Session, client: Client) -> schemas.ClientDetailOut:
    unames = common.user_name_map(db, [client.manager_id])
    subs = (
        db.query(ReportSubscription)
        .filter(ReportSubscription.client_id == client.client_id)
        .order_by(ReportSubscription.created_at.asc())
        .all()
    )
    out = schemas.ClientDetailOut.model_validate(client, from_attributes=True)
    return out.model_copy(
        update={
            "manager_name": unames.get(client.manager_id),
            "subscriptions": [
                schemas.ReportSubscriptionOut.model_validate(s, from_attributes=True)
                for s in subs
            ],
        }
    )


@router.get("", response_model=schemas.ClientListResponse)
def list_clients(
    client_type: Optional[str] = Query(None, description="TRANSPORT/FACILITY"),
    contract_status: Optional[str] = Query(None, description="ACTIVE/HOLD/END"),
    manager_id: Optional[str] = Query(None, description="담당 PM"),
    search: Optional[str] = Query(None, description="고객사명·주 담당자·사업자번호 검색"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """고객사 목록 (SCR-03) — 기본 '전체 고객사' (공동 관리)."""
    query = db.query(Client)
    if client_type:
        query = query.filter(Client.client_type == client_type)
    if contract_status:
        query = query.filter(Client.contract_status == contract_status)
    if manager_id:
        query = query.filter(Client.manager_id == manager_id)
    if search:
        keyword = "%{0}%".format(search.strip())
        query = query.filter(
            or_(
                Client.company_name.ilike(keyword),
                Client.main_contact_name.ilike(keyword),
                Client.biz_reg_no.like(keyword),
            )
        )

    total = query.count()
    rows = (
        query.order_by(Client.company_name.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    ids = [c.client_id for c in rows]
    unames = common.user_name_map(db, [c.manager_id for c in rows])

    # 최근 활동 일시
    last_map = {}
    if ids:
        last_rows = (
            db.query(ActivityHistory.client_id, func.max(ActivityHistory.activity_date))
            .filter(ActivityHistory.client_id.in_(ids))
            .group_by(ActivityHistory.client_id)
            .all()
        )
        last_map = {cid: dt for cid, dt in last_rows}

    # 이번 달 보고서 상태 미니 배지 — 당월 발송 건 중 가장 최근 갱신분
    report_map = {}
    if ids:
        period = common.current_period()
        deliveries = (
            db.query(ReportDelivery)
            .filter(ReportDelivery.period == period, ReportDelivery.client_id.in_(ids))
            .order_by(ReportDelivery.updated_at.asc())
            .all()
        )
        for d in deliveries:
            report_map[d.client_id] = d.status

    # 성공 보수율 🔒 — 참여 사업 map 중 최대값 (프론트 마스킹 대상)
    fee_map = {}
    if ids:
        fee_rows = (
            db.query(ProjectClientMap.client_id, func.max(ProjectClientMap.success_fee_rate))
            .filter(ProjectClientMap.client_id.in_(ids))
            .group_by(ProjectClientMap.client_id)
            .all()
        )
        fee_map = {cid: (float(v) if v is not None else None) for cid, v in fee_rows}

    items = []
    for c in rows:
        out = schemas.ClientListItem.model_validate(c, from_attributes=True)
        items.append(
            out.model_copy(
                update={
                    "manager_name": unames.get(c.manager_id),
                    "last_activity_at": last_map.get(c.client_id),
                    "report_status_this_month": report_map.get(c.client_id),
                    "success_fee_rate": fee_map.get(c.client_id),
                }
            )
        )
    return schemas.ClientListResponse(items=items, total=total)


@router.post("", response_model=schemas.ClientDetailOut, status_code=201)
def create_client(
    payload: schemas.ClientCreate,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """고객사 등록 (SCR-03) — 월간 보고서 설정(subscription) 동시 등록 지원."""
    if payload.manager_id:
        common.get_or_404(db, User, payload.manager_id, "담당 PM")
    client = Client(**{f: getattr(payload, f) for f in _CLIENT_FIELDS})
    db.add(client)
    db.flush()
    if payload.subscription:
        _upsert_subscription(db, client, payload.subscription)
    db.commit()
    db.refresh(client)
    return _client_detail(db, client)


@router.get("/{client_id}", response_model=schemas.ClientDetailOut)
def get_client(
    client_id: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """고객사 상세 — 360° 뷰 개요 탭 (SCR-03D)."""
    client = common.get_or_404(db, Client, client_id, "고객사")
    return _client_detail(db, client)


@router.put("/{client_id}", response_model=schemas.ClientDetailOut)
def update_client(
    client_id: str,
    payload: schemas.ClientUpdate,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """고객사 수정 — 전달된 필드만 반영."""
    client = common.get_or_404(db, Client, client_id, "고객사")
    data = payload.model_dump(exclude_unset=True)
    if data.get("manager_id"):
        common.get_or_404(db, User, data["manager_id"], "담당 PM")
    for field in _CLIENT_FIELDS:
        if field in data:
            setattr(client, field, data[field])
    if payload.subscription:
        _upsert_subscription(db, client, payload.subscription)
    db.commit()
    db.refresh(client)
    return _client_detail(db, client)


# ---------------------------------------------------------------------------
# 서브리소스 (SCR-03D 탭)
# ---------------------------------------------------------------------------
@router.get("/{client_id}/histories", response_model=List[schemas.HistoryOut])
def client_histories(
    client_id: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """활동 이력 탭 — 시간 역순 타임라인."""
    common.get_or_404(db, Client, client_id, "고객사")
    rows = (
        db.query(ActivityHistory)
        .filter(ActivityHistory.client_id == client_id)
        .order_by(ActivityHistory.activity_date.desc())
        .all()
    )
    return common.build_history_outs(db, rows)


@router.get("/{client_id}/reports", response_model=List[schemas.ReportRow])
def client_reports(
    client_id: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """보고서·문서 탭 — 월별 보고서 발송 이력."""
    common.get_or_404(db, Client, client_id, "고객사")
    rows = (
        db.query(ReportDelivery)
        .filter(ReportDelivery.client_id == client_id)
        .order_by(ReportDelivery.period.desc(), ReportDelivery.report_type.asc())
        .all()
    )
    return common.build_report_rows(db, rows)


@router.get("/{client_id}/documents", response_model=List[schemas.DocumentOut])
def client_documents(
    client_id: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """보고서·문서 탭 — 고객사 문서함."""
    common.get_or_404(db, Client, client_id, "고객사")
    rows = (
        db.query(Document)
        .filter(Document.client_id == client_id)
        .order_by(Document.created_at.desc())
        .all()
    )
    return common.build_document_outs(db, rows)


@router.get("/{client_id}/assets", response_model=List[schemas.AssetOut])
def client_assets(
    client_id: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """자산 및 연동 탭 — 인증정보 값은 미노출(설정 여부만, reveal은 P2)."""
    common.get_or_404(db, Client, client_id, "고객사")
    rows = (
        db.query(Asset)
        .filter(Asset.client_id == client_id)
        .order_by(Asset.created_at.asc())
        .all()
    )
    return [
        schemas.AssetOut.model_validate(a, from_attributes=True).model_copy(
            update={"has_credentials": bool(a.login_password or a.api_token)}
        )
        for a in rows
    ]
