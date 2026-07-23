"""고객사 마스터 — SCR-03 목록/등록·SCR-03D 360° 뷰 (P1).

- 목록: FilterBar(구분·계약 상태·담당 PM·검색) + 최근 활동 일시 + 이번 달 보고서 상태 미니 배지
- 상세: 개요(구독 설정 포함) + 서브리소스(활동 이력/보고서/문서/자산)
- 민감 필드(success_fee_rate)는 응답에 포함하되 프론트가 마스킹 (reveal 감사 로그는 P2)
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_permission
from models import (
    ActivityHistory,
    Asset,
    Client,
    Document,
    Project,
    ProjectClientMap,
    ReportDelivery,
    ReportRecipient,
    ReportSubscription,
    SessionLocal,
    User,
    get_db,
)
from routers import common
from routers.codes import validate_active_code
from services import client_folders, dropbox_storage
from services.audit_logger import AuditLogger

log = logging.getLogger(__name__)

router = APIRouter(prefix="/clients", tags=["clients"])


def _provision_dropbox_folder_bg(client_id: str, actor_id: Optional[str] = None) -> None:
    """등록 응답 이후 백그라운드로 Dropbox 전용 폴더 생성 (best-effort).

    등록 요청 스레드를 블로킹하지 않도록 응답 후 실행되며, 자체 DB 세션을 연다.
    Dropbox 미설정이면 조용히 스킵되고, 생성 실패(API·네트워크·지연)는 등록에 영향을
    주지 않는다(이미 커밋됨). 실패분은 백필(POST /batch/provision-dropbox-folders)로 복구.
    actor_id는 폴더 생성 감사 로그(CLIENT_FOLDER_PROVISION)의 처리자로 기록된다.
    """
    db = SessionLocal()
    try:
        client = db.get(Client, client_id)
        if client is None:
            return
        result = client_folders.provision(db, client, actor_id=actor_id)
        if not result.get("skipped"):
            db.commit()
    except Exception:
        db.rollback()
        log.warning(
            "Dropbox 폴더 provision 실패 (client_id=%s)", client_id, exc_info=True
        )
    finally:
        db.close()

_CLIENT_FIELDS = [
    "client_type", "company_name", "biz_reg_no", "region", "address",
    "ceo_name", "ceo_contact_phone", "ceo_contact_email",
    "main_contact_name", "main_contact_phone", "main_contact_email",
    "contract_status", "contract_date", "keyman", "manager_id",
    "report_yn", "lat", "lng",
]


# 사업자번호 정규화·중복 검사 — 엑셀 일괄 등록과 공유하기 위해 common.py로 승격.
# 기존 내부 이름은 import 별칭으로 유지(동작 불변).
_normalize_biz_no = common.normalize_biz_no
_check_biz_reg_no_duplicate = common.check_biz_reg_no_duplicate


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
    sub.mail_subject = sub_in.mail_subject  # null=전역 기본 템플릿 사용
    sub.mail_body = sub_in.mail_body
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
        keyword = "%{0}%".format(common.escape_like(search.strip()))
        query = query.filter(
            or_(
                Client.company_name.ilike(keyword, escape="\\"),
                Client.main_contact_name.ilike(keyword, escape="\\"),
                Client.biz_reg_no.like(keyword, escape="\\"),
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
    background_tasks: BackgroundTasks,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """고객사 등록 (SCR-03) — 월간 보고서 설정(subscription) 동시 등록 지원."""
    validate_active_code(db, "CLIENT_TYPE", payload.client_type)
    validate_active_code(db, "CONTRACT_STATUS", payload.contract_status)
    _check_biz_reg_no_duplicate(db, payload.biz_reg_no)
    if payload.manager_id:
        common.get_or_404(db, User, payload.manager_id, "담당 PM")
    client = Client(**{f: getattr(payload, f) for f in _CLIENT_FIELDS})
    db.add(client)
    db.flush()
    if payload.subscription:
        _upsert_subscription(db, client, payload.subscription)
    db.commit()
    db.refresh(client)
    # 등록 응답을 블로킹하지 않도록 폴더 생성은 응답 후 백그라운드로 (실패는 백필 복구)
    background_tasks.add_task(_provision_dropbox_folder_bg, client.client_id, user.user_id)
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
    # client_type은 '변경될 때만' 활성 검증 — 은퇴(비활성) 코드를 쓰던 기존 고객사도
    # 다른 필드 수정이 막히지 않게(값 유지는 허용, 비활성 코드로 새로 바꾸는 것만 차단).
    if "client_type" in data and data["client_type"] != client.client_type:
        validate_active_code(db, "CLIENT_TYPE", data["client_type"])
    if "contract_status" in data:
        validate_active_code(db, "CONTRACT_STATUS", data["contract_status"])
    if "biz_reg_no" in data:
        _check_biz_reg_no_duplicate(db, data["biz_reg_no"], exclude_client_id=client_id)
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


@router.get("/{client_id}/projects", response_model=List[schemas.ClientProjectRow])
def client_projects(
    client_id: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """참여 사업·정산 탭 — 매핑+사업 조인. 보수율·예상 정산액 🔒은 프론트 마스킹."""
    common.get_or_404(db, Client, client_id, "고객사")
    rows = (
        db.query(ProjectClientMap)
        .filter(ProjectClientMap.client_id == client_id)
        .order_by(ProjectClientMap.created_at.asc())
        .all()
    )
    projects = {
        p.project_id: p
        for p in db.query(Project)
        .filter(Project.project_id.in_({m.project_id for m in rows}))
        .all()
    } if rows else {}
    items = []
    for m in rows:
        p = projects.get(m.project_id)
        items.append(
            schemas.ClientProjectRow(
                map_id=m.map_id,
                project_id=m.project_id,
                project_name=p.project_name if p else None,
                project_status=p.project_status if p else None,
                allocation_ratio=float(m.allocation_ratio) if m.allocation_ratio is not None else None,
                success_fee_rate=float(m.success_fee_rate) if m.success_fee_rate is not None else None,
                expected_amount=float(m.expected_amount) if m.expected_amount is not None else None,
                settlement_status=m.settlement_status or "STANDBY",
                billed_at=m.billed_at,
                completed_at=m.completed_at,
            )
        )
    return items


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


# ---------------------------------------------------------------------------
# 보고서 수신자 (tb_report_recipient) — P1-C 기능 공백 보강
# ---------------------------------------------------------------------------
@router.get("/{client_id}/recipients", response_model=List[schemas.RecipientOut])
def client_recipients(
    client_id: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """수신자 목록 — 공통분(sub_id null) + 구독 지정분 전체. 해석 규칙은 resolve_recipients(R2-B5)."""
    common.get_or_404(db, Client, client_id, "고객사")
    rows = (
        db.query(ReportRecipient)
        .filter(ReportRecipient.client_id == client_id)
        .order_by(ReportRecipient.created_at.asc())
        .all()
    )
    return [schemas.RecipientOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/{client_id}/recipients", response_model=schemas.RecipientOut, status_code=201)
def add_recipient(
    client_id: str,
    payload: schemas.RecipientCreate,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """수신자 등록 — sub_id null=전 유형 공통(R2-B8), 같은 (고객사, 이메일, sub_id) 중복 409."""
    common.get_or_404(db, Client, client_id, "고객사")
    if payload.sub_id:
        sub = common.get_or_404(db, ReportSubscription, payload.sub_id, "보고서 구독")
        if sub.client_id != client_id:
            raise HTTPException(status_code=422, detail="해당 고객사의 보고서 구독이 아닙니다")
    duplicate = (
        db.query(ReportRecipient)
        .filter(
            ReportRecipient.client_id == client_id,
            func.lower(ReportRecipient.email) == payload.email.lower(),
            (
                ReportRecipient.sub_id == payload.sub_id
                if payload.sub_id
                else ReportRecipient.sub_id.is_(None)
            ),
        )
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="이미 등록된 수신자입니다")
    recipient = ReportRecipient(
        client_id=client_id,
        email=payload.email,
        name=payload.name,
        cc_yn=payload.cc_yn,
        sub_id=payload.sub_id,
    )
    db.add(recipient)
    db.flush()  # gen_uuid PK 확보 후 감사 로그 target_id로 사용
    # 감사 로그 — 이메일은 비밀값 아님(R2-E6 검토), 발송 추적 취지상 기록
    AuditLogger.log_action(
        db,
        user.user_id,
        "RECIPIENT_ADD",
        target_type="CLIENT",
        target_id=client_id,
        new_value="{0} ({1}{2})".format(
            recipient.email,
            "CC" if recipient.cc_yn == "Y" else "TO",
            ", 구독 지정" if recipient.sub_id else ", 공통",
        ),
    )
    db.commit()
    db.refresh(recipient)
    return schemas.RecipientOut.model_validate(recipient, from_attributes=True)


@router.delete("/{client_id}/recipients/{recipient_id}", response_model=schemas.MessageResponse)
def remove_recipient(
    client_id: str,
    recipient_id: str,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """수신자 삭제 — 다른 고객사 수신자는 404 (경로-소유 일치 가드)."""
    common.get_or_404(db, Client, client_id, "고객사")
    recipient = db.get(ReportRecipient, recipient_id)
    if recipient is None or recipient.client_id != client_id:
        raise HTTPException(status_code=404, detail="수신자를 찾을 수 없습니다")
    AuditLogger.log_action(
        db,
        user.user_id,
        "RECIPIENT_REMOVE",
        target_type="CLIENT",
        target_id=client_id,
        old_value="{0} ({1})".format(
            recipient.email, "CC" if recipient.cc_yn == "Y" else "TO"
        ),
    )
    db.delete(recipient)
    db.commit()
    return schemas.MessageResponse(message="수신자가 삭제되었습니다")


@router.get("/{client_id}/dropbox/tree", response_model=schemas.DropboxTreeResponse)
def get_client_dropbox_tree(
    client_id: str,
    path: Optional[str] = Query(None, description="조회 폴더 경로(미지정 시 고객사 루트)"),
    user: User = Depends(require_permission("crm.read_write")),
    db: Session = Depends(get_db),
):
    """고객사 Dropbox 폴더 라이브 조회 — 발송 첨부 선택용.

    경로는 반드시 해당 고객사 폴더 하위로 제한(confinement). 미provision 409,
    Dropbox 미설정 503, 없는 경로 404.
    """
    client = common.get_or_404(db, Client, client_id, "고객사")
    if not client.dropbox_folder:
        raise HTTPException(
            status_code=409,
            detail="이 고객사는 아직 Dropbox 폴더가 생성되지 않았습니다. 폴더 생성(백필) 후 이용하세요.",
        )
    if not dropbox_storage.is_configured():
        raise HTTPException(status_code=503, detail="Dropbox 연동이 설정되지 않았습니다.")

    target = client_folders.normalize_dropbox_path(path or client.dropbox_folder)
    if not client_folders.is_within_client_folder(client, target):
        raise HTTPException(status_code=403, detail="고객사 폴더 밖의 경로에는 접근할 수 없습니다.")

    try:
        entries = dropbox_storage.list_folder(target)
    except dropbox_storage.DropboxNotFound:
        # 루트 폴더 자체가 없음 = 외부(수동) 삭제 신호 → 감사 로그로 근거를 남긴다(오명 방지).
        # 하위 경로 404(오래된 링크 재요청 등)는 잡음이라 제외하고 루트 소실만 기록. 경로만(R2-E6).
        if target == client_folders.normalize_dropbox_path(client.dropbox_folder):
            AuditLogger.log_action(
                db, user.user_id, "CLIENT_FOLDER_MISSING",
                target_type="CLIENT", target_id=client_id, new_value=target,
            )
            db.commit()
        raise HTTPException(status_code=404, detail="해당 경로를 찾을 수 없습니다.")
    except dropbox_storage.DropboxConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    return schemas.DropboxTreeResponse(
        path=target,
        entries=[schemas.DropboxEntry(**e) for e in entries],
    )
