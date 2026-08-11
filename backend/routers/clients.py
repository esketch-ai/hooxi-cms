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
    ChatMessage,
    ChatThread,
    Client,
    ClientVehicle,
    Document,
    IssueComment,
    KakaoContact,
    Project,
    ProjectClientMap,
    ProjectVehicle,
    ReportDelivery,
    ReportRecipient,
    ReportSendLog,
    ReportSubscription,
    Schedule,
    SegmentSendLog,
    SessionLocal,
    User,
    get_db,
)
from routers import common
from routers.codes import validate_active_code
from services import client_folders, dropbox_storage, geocoding
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


def _geocode_client_bg(client_id: str, force: bool = False) -> None:
    """등록·수정 이후 백그라운드로 주소→좌표 지오코딩 (best-effort, SCR-09 지도).

    자체 DB 세션을 열고, 키 미설정이면 조용히 스킵. 좌표가 이미 있으면 force=True일 때만
    갱신하며, 지오코딩 실패 시엔 기존 좌표를 지우지 않는다(빈 값보다 옛 좌표가 낫다).
    실패는 등록/수정에 영향을 주지 않고, 백필(POST /clients/geocode-missing)로 복구 가능.
    """
    if not geocoding.is_configured():
        return
    db = SessionLocal()
    try:
        client = db.get(Client, client_id)
        if client is None:
            return
        if not force and client.lat is not None and client.lng is not None:
            return
        hit = geocoding.geocode(client.address, client.region)
        if hit is None:
            return
        client.lat, client.lng = hit
        db.commit()
    except Exception:
        db.rollback()
        log.warning("지오코딩 실패 (client_id=%s)", client_id, exc_info=True)
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
    validate_active_code(db, "REGION", payload.region)
    _check_biz_reg_no_duplicate(db, payload.biz_reg_no)
    # 사업자번호 없이 간편 등록되는 경로(ActivityForm 인라인)는 위 검사를 우회하므로,
    # 그 경우 회사명 기준 중복도 막는다(더블클릭 중복 생성 차단).
    if not common.normalize_biz_no(payload.biz_reg_no):
        common.check_company_name_duplicate(db, payload.company_name, payload.client_type)
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
    # 좌표 미제공 시 주소→좌표 지오코딩(백그라운드, best-effort) — helper가 좌표 유무를 재확인
    if client.lat is None or client.lng is None:
        background_tasks.add_task(_geocode_client_bg, client.client_id)
    return _client_detail(db, client)


@router.post("/geocode-missing", response_model=schemas.GeocodeBackfillResult)
def geocode_missing_clients(
    limit: int = Query(30, ge=1, le=50),
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """좌표 미등록 고객사 일괄 지오코딩 (SCR-09 지도) — 배치당 최대 limit건.

    주소나 지역이 있으나 lat/lng가 비어있는 고객사를 카카오 로컬로 좌표화한다.
    한 요청이 오래 붙잡히지 않도록 배치 상한을 두고, 성공분은 건별로 즉시 커밋해
    도중 타임아웃이 나도 이미 채운 좌표가 유실되지 않게 한다. 남은 건수를 함께 반환한다.
    """
    if not geocoding.is_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "카카오 지도 REST API 키가 설정되지 않아 지오코딩할 수 없습니다. "
                "환경설정 > 연동에서 '카카오 지도' REST API 키를 등록하세요."
            ),
        )
    has_locus = or_(
        (Client.address.isnot(None)) & (Client.address != ""),
        (Client.region.isnot(None)) & (Client.region != ""),
    )
    missing_coords = or_(Client.lat.is_(None), Client.lng.is_(None))
    base = db.query(Client).filter(missing_coords, has_locus)
    remaining_total = base.count()
    rows = base.limit(limit).all()
    updated = 0
    for c in rows:
        hit = geocoding.geocode(c.address, c.region)
        if hit is not None:
            c.lat, c.lng = hit
            db.commit()  # 성공분 즉시 보존 (배치 도중 타임아웃 대비)
            updated += 1
    return schemas.GeocodeBackfillResult(
        updated=updated,
        failed=len(rows) - updated,
        remaining=max(0, remaining_total - updated),
    )


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
    background_tasks: BackgroundTasks,
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
    # region도 '변경될 때만' 검증 — 레거시 비표준 지역값을 쓰던 고객사의 타 필드 수정을 막지 않음
    if "region" in data and data["region"] != client.region:
        validate_active_code(db, "REGION", data["region"])
    if "biz_reg_no" in data:
        _check_biz_reg_no_duplicate(db, data["biz_reg_no"], exclude_client_id=client_id)
    if data.get("manager_id"):
        common.get_or_404(db, User, data["manager_id"], "담당 PM")
    # 지오코딩 재계산 판단용 — 실제 주소·지역 변경 여부를 이전 값과 비교(프론트가 값을 항상
    # 실어보내므로 'data에 키 존재'만으론 부족). setattr 전에 스냅샷.
    prev_address, prev_region = client.address, client.region
    for field in _CLIENT_FIELDS:
        if field in data:
            setattr(client, field, data[field])
    if payload.subscription:
        _upsert_subscription(db, client, payload.subscription)
    db.commit()
    db.refresh(client)
    # 주소·지역이 실제로 바뀌었고 좌표를 직접 지정하지 않았다면 좌표 재계산(백그라운드, best-effort)
    addr_changed = client.address != prev_address or client.region != prev_region
    if addr_changed and not ("lat" in data or "lng" in data):
        background_tasks.add_task(_geocode_client_bg, client.client_id, True)
    return _client_detail(db, client)


# 고객사 삭제 시 종속 데이터 검사 대상 — (사용자 표시 라벨, 모델)
_CLIENT_DEP_CHECKS = [
    ("활동이력", ActivityHistory),
    ("사업", Project),
    ("사업-고객사 매핑", ProjectClientMap),
    ("사업 참여 차량", ProjectVehicle),
    ("보유 차량", ClientVehicle),
    ("자산", Asset),
    ("일정", Schedule),
    ("보고서 발송", ReportDelivery),
    ("보고서 구독", ReportSubscription),
    ("보고서 수신자", ReportRecipient),
    ("문서", Document),
    ("카카오 연락처", KakaoContact),
    ("채팅 스레드", ChatThread),
    ("세그먼트 발송 이력", SegmentSendLog),
]


def _client_dependents(db: Session, client_id: str) -> List[str]:
    """고객사에 연결된 종속 데이터의 종류(존재하는 것만) 반환 — 삭제 가드용."""
    present = []
    for label, model in _CLIENT_DEP_CHECKS:
        if db.query(model).filter(model.client_id == client_id).first() is not None:
            present.append(label)
    return present


def _has_project_or_settlement(db: Session, client_id: str) -> bool:
    """사업 참여(매핑)·대표사 지정 여부 — 강제 삭제여도 차단해 재무기록·공유 사업을 보호."""
    if db.query(ProjectClientMap).filter(ProjectClientMap.client_id == client_id).first():
        return True
    if db.query(Project).filter(Project.client_id == client_id).first():
        return True
    return False


def _cascade_delete_client(db: Session, client_id: str):
    """고객사의 종속 데이터를 FK 의존 순서로 정리(사업/정산은 호출 전 차단됨).

    Document↔ReportDelivery 순환참조와 자기참조(Schedule.parent, History.related)는 참조를 먼저
    끊고(null) 자식→부모 순으로 삭제한다.
    """
    q = db.query
    hist_ids = [r[0] for r in q(ActivityHistory.history_id).filter(ActivityHistory.client_id == client_id)]
    asset_ids = [r[0] for r in q(Asset.asset_id).filter(Asset.client_id == client_id)]
    delivery_ids = [r[0] for r in q(ReportDelivery.report_id).filter(ReportDelivery.client_id == client_id)]
    contact_ids = [r[0] for r in q(KakaoContact.contact_id).filter(KakaoContact.client_id == client_id)]
    thread_ids = {r[0] for r in q(ChatThread.thread_id).filter(ChatThread.client_id == client_id)}
    if contact_ids:
        thread_ids |= {r[0] for r in q(ChatThread.thread_id).filter(ChatThread.kakao_contact_id.in_(contact_ids))}
    thread_ids = list(thread_ids)

    sched_conds = [Schedule.client_id == client_id]
    if hist_ids:
        sched_conds.append(Schedule.history_id.in_(hist_ids))
    sched_ids = [r[0] for r in q(Schedule.schedule_id).filter(or_(*sched_conds))]

    doc_conds = [Document.client_id == client_id]
    if hist_ids:
        doc_conds.append(Document.history_id.in_(hist_ids))
    if asset_ids:
        doc_conds.append(Document.asset_id.in_(asset_ids))
    if delivery_ids:
        doc_conds.append(Document.report_id.in_(delivery_ids))
    doc_ids = [r[0] for r in q(Document.doc_id).filter(or_(*doc_conds))]

    def dele(model, cond):
        q(model).filter(cond).delete(synchronize_session=False)

    # 1) 2차 자식 삭제
    if thread_ids:
        dele(ChatMessage, ChatMessage.thread_id.in_(thread_ids))
    if hist_ids:
        dele(IssueComment, IssueComment.history_id.in_(hist_ids))
    if delivery_ids:
        dele(ReportSendLog, ReportSendLog.report_id.in_(delivery_ids))
    # 2) 순환/자기 참조 끊기 (삭제 대상 문서·스케줄·이력을 가리키는 참조를 null)
    if doc_ids:
        q(ReportDelivery).filter(ReportDelivery.doc_id.in_(doc_ids)).update({"doc_id": None}, synchronize_session=False)
        q(ReportDelivery).filter(ReportDelivery.pinned_doc_id.in_(doc_ids)).update({"pinned_doc_id": None}, synchronize_session=False)
        q(ReportSendLog).filter(ReportSendLog.sent_doc_id.in_(doc_ids)).update({"sent_doc_id": None}, synchronize_session=False)
    if sched_ids:
        q(Schedule).filter(Schedule.parent_schedule_id.in_(sched_ids)).update({"parent_schedule_id": None}, synchronize_session=False)
    if hist_ids:
        q(ActivityHistory).filter(ActivityHistory.related_history_id.in_(hist_ids)).update({"related_history_id": None}, synchronize_session=False)
    # 3) 자식→부모 순 삭제
    if doc_ids:
        dele(Document, Document.doc_id.in_(doc_ids))
    if sched_ids:
        dele(Schedule, Schedule.schedule_id.in_(sched_ids))
    if thread_ids:
        dele(ChatThread, ChatThread.thread_id.in_(thread_ids))
    dele(KakaoContact, KakaoContact.client_id == client_id)
    dele(ActivityHistory, ActivityHistory.client_id == client_id)
    dele(ReportRecipient, ReportRecipient.client_id == client_id)
    dele(ReportSubscription, ReportSubscription.client_id == client_id)
    dele(ReportDelivery, ReportDelivery.client_id == client_id)
    # 사업 참여 차량 — 이 고객사(운수사)/자산 참조를 끊어 프로젝트 차량은 보존(자산 삭제 전 실행)
    q(ProjectVehicle).filter(ProjectVehicle.client_id == client_id).update(
        {"client_id": None}, synchronize_session=False
    )
    # 보유 차량(fleet) — 운수사 참조만 끊어 마스터는 보존(부록 M, 참여 링크는 유지)
    q(ClientVehicle).filter(ClientVehicle.client_id == client_id).update(
        {"client_id": None}, synchronize_session=False
    )
    if asset_ids:
        q(ProjectVehicle).filter(ProjectVehicle.asset_id.in_(asset_ids)).update(
            {"asset_id": None}, synchronize_session=False
        )
        q(ClientVehicle).filter(ClientVehicle.asset_id.in_(asset_ids)).update(
            {"asset_id": None}, synchronize_session=False
        )
    dele(Asset, Asset.client_id == client_id)
    dele(SegmentSendLog, SegmentSendLog.client_id == client_id)


@router.delete("/{client_id}", response_model=schemas.MessageResponse)
def delete_client(
    client_id: str,
    force: bool = Query(False, description="종속 데이터까지 강제 삭제"),
    confirm_name: Optional[str] = Query(None, description="강제 삭제 시 담당자 본인 이름 확인"),
    user: User = Depends(require_permission("client.delete")),
    db: Session = Depends(get_db),
):
    """고객사 삭제 (MANAGER·ADMIN).

    - 기본: 연결된 종속 데이터가 없을 때만 삭제. 있으면 409 + '계약 종료' 안내.
    - 강제(force=true): 재확인 + 담당자 본인 이름(confirm_name==로그인 사용자명) 일치 시 종속까지
      캐스케이드 삭제. 단 사업 참여·정산이 있으면 재무기록·공유 사업 보호를 위해 강제여도 차단.
      모든 강제 삭제는 감사 로그(CLIENT_FORCE_DELETE)에 담당자·확인명·종속 요약을 남긴다.
    """
    client = common.get_or_404(db, Client, client_id, "고객사")
    dependents = _client_dependents(db, client_id)

    if not dependents:
        AuditLogger.log_action(
            db, user.user_id, "CLIENT_DELETE", target_type="CLIENT", target_id=client_id,
            old_value="{0} ({1})".format(client.company_name, client.client_type),
        )
        db.delete(client)
        db.commit()
        return schemas.MessageResponse(message="고객사가 삭제되었습니다")

    if not force:
        raise HTTPException(
            status_code=409,
            detail="연결된 데이터가 있어 삭제할 수 없습니다 ({0}). 계약 상태를 '종료'로 변경하세요.".format(
                ", ".join(dependents)
            ),
        )

    # 강제 삭제 — 사업/정산은 강제여도 차단(재무기록·공유 사업 보호)
    if _has_project_or_settlement(db, client_id):
        raise HTTPException(
            status_code=409,
            detail="사업 참여·정산 정보가 있어 강제 삭제할 수 없습니다. 먼저 해당 사업에서 제외하고 정산을 정리하세요.",
        )
    # 담당자 본인 이름 확인 (책임성)
    if not confirm_name or confirm_name.strip() != (user.name or "").strip():
        raise HTTPException(
            status_code=403,
            detail="담당자 본인 이름이 일치하지 않아 강제 삭제를 진행할 수 없습니다.",
        )

    AuditLogger.log_action(
        db, user.user_id, "CLIENT_FORCE_DELETE", target_type="CLIENT", target_id=client_id,
        old_value="{0} ({1}) 강제삭제 — 확인:{2}, 종속:{3}".format(
            client.company_name, client.client_type, confirm_name.strip(), ", ".join(dependents)
        ),
    )
    _cascade_delete_client(db, client_id)
    db.delete(client)
    db.commit()
    return schemas.MessageResponse(message="고객사가 강제 삭제되었습니다")


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


@router.get("/{client_id}/dropbox/file", response_model=schemas.DropboxFileLinkOut)
def get_client_dropbox_file_link(
    client_id: str,
    path: str = Query(..., description="열람할 파일의 Dropbox 경로(고객사 폴더 하위)"),
    user: User = Depends(require_permission("crm.read_write")),
    db: Session = Depends(get_db),
):
    """고객사 Dropbox 폴더 내 파일 임시 열람 링크 — 문서 아카이브 'Dropbox 폴더 보기'용.

    확인(confinement) 필수: 고객사 폴더 하위 경로만 허용. 미provision 409, 미설정 503,
    폴더 밖 403, 없음/폴더 404. 앱 문서 레코드가 없어도 Dropbox에 직접 넣은 파일을 연다.
    """
    client = common.get_or_404(db, Client, client_id, "고객사")
    if not client.dropbox_folder:
        raise HTTPException(status_code=409, detail="이 고객사는 아직 Dropbox 폴더가 생성되지 않았습니다.")
    if not dropbox_storage.is_configured():
        raise HTTPException(status_code=503, detail="Dropbox 연동이 설정되지 않았습니다.")

    target = client_folders.normalize_dropbox_path(path)
    if not client_folders.is_within_client_folder(client, target):
        raise HTTPException(status_code=403, detail="고객사 폴더 밖의 경로에는 접근할 수 없습니다.")

    try:
        url = dropbox_storage.temporary_link(target)  # 실패 시 None(파일 아님/삭제)
    except dropbox_storage.DropboxConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if not url:
        raise HTTPException(status_code=404, detail="해당 파일을 찾을 수 없습니다.")

    # 파일 열람 감사 — 경로만 기록(R2-E6). Dropbox 폴더 열람 추적.
    AuditLogger.log_action(
        db, user.user_id, "CLIENT_FOLDER_FILE_OPEN",
        target_type="CLIENT", target_id=client_id, new_value=target,
    )
    db.commit()
    return schemas.DropboxFileLinkOut(url=url)
