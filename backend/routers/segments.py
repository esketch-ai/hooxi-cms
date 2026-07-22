"""세그먼트 보고서 발송 — 조건 기반 고객사 묶음 (SCR-12 확장, tb_segment).

- 세그먼트: 조건(criteria)의 저장본. 축 간 AND, 축 내 IN(OR).
- preview: 조건에 맞는 고객사 목록 + 수신 가능 여부(can_receive) 미리보기.
- facets: region 축 선택지(나머지 축은 프론트가 /codes·/projects 재사용).
- 발송 실행(B5): POST /segments/send(즉석)·/segments/{id}/send(저장 세그먼트) —
  tb_segment_send + 고객사별 tb_segment_send_log 적재, 건별 실패 격리.

핵심 정합성: project_id·settlement_status는 '같은 ProjectClientMap 행'에서 함께
평가하는 EXISTS 서브쿼리 1개로 처리한다 — 사업 A 참여 + 사업 B에서만 BILLED인
회사가 (A참여 AND BILLED) 조건에 잘못 포함되는 것을 방지.
"""

import json
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
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
    ReportRecipient,
    Segment,
    SegmentSend,
    SegmentSendLog,
    User,
    get_db,
)
from routers import common
from routers.codes import validate_active_code
from services import client_folders, dropbox_storage, email_service, storage
from services.audit_logger import AuditLogger
from services.report_sender import render_template, resolve_recipients

router = APIRouter(prefix="/segments", tags=["segments"])


@router.get("/dropbox/tree", response_model=schemas.DropboxTreeResponse)
def get_public_dropbox_tree(
    path: Optional[str] = Query(None, description="조회 폴더 경로(미지정 시 공용 발송자료 루트)"),
    _: User = Depends(require_permission("master.write")),
):
    """세그먼트 공용 발송자료 Dropbox 폴더 라이브 조회 — 발송 첨부 선택용.

    경로는 공용 발송자료 폴더(공용_발송자료) 하위로 제한(confinement). 루트가 없으면
    자동 생성 후 빈 목록. Dropbox 미설정 503, 경계 밖 403, 없는 하위 경로 404.
    """
    if not dropbox_storage.is_configured():
        raise HTTPException(status_code=503, detail="Dropbox 연동이 설정되지 않았습니다.")
    root = client_folders.public_send_root()
    target = client_folders.normalize_dropbox_path(path or root)
    if not client_folders.is_within_folder(root, target):
        raise HTTPException(
            status_code=403, detail="공용 발송자료 폴더 밖의 경로에는 접근할 수 없습니다."
        )
    try:
        entries = dropbox_storage.list_folder(target)
    except dropbox_storage.DropboxNotFound:
        if target == root:
            dropbox_storage.ensure_folder(root)  # 최초 조회 시 공용 루트 자동 생성
            entries = []
        else:
            raise HTTPException(status_code=404, detail="해당 경로를 찾을 수 없습니다.")
    except dropbox_storage.DropboxConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return schemas.DropboxTreeResponse(
        path=target, entries=[schemas.DropboxEntry(**e) for e in entries]
    )

# criteria 축 → 공통 코드 카테고리 매핑 (region은 자유값, project_id는 존재 검증)
CRITERIA_CODE_CATEGORIES = {
    "client_type": "CLIENT_TYPE",
    "contract_status": "CONTRACT_STATUS",
    "asset_group": "ASSET_GROUP",
    "settlement_status": "SETTLEMENT_STATUS",
}

# 세그먼트용 기본 메일 문구 — SegmentsPage.tsx DEFAULT_SUBJECT/BODY와 동일해야 함.
# 월간 보고서 템플릿(DEFAULT_REPORT_MAIL_*·tb_config report_mail_*)의 {보고서유형}은
# 세그먼트 발송 변수에 없어 리터럴로 발송되므로 폴백으로 사용 금지.
# 사용 가능 변수: {고객사명} {연도} {월} {담당자명}
DEFAULT_SEGMENT_MAIL_SUBJECT = "[Hooxi] {고객사명} 안내 자료 송부"
DEFAULT_SEGMENT_MAIL_BODY = (
    "{고객사명} 담당자님, 안녕하세요.\n"
    "후시파트너스입니다.\n\n"
    "{연도}년 {월}월 안내 자료를 첨부와 같이 송부드립니다.\n"
    "확인 부탁드리며, 문의 사항은 본 메일로 회신 주시기 바랍니다.\n\n"
    "감사합니다.\n"
    "{담당자명} 드림"
)

# 첨부 총량 상한 — Gmail 첨부 한도(25MB)보다 보수적으로 사전 차단
MAX_ATTACHMENT_TOTAL_BYTES = 20 * 1024 * 1024


# ---------------------------------------------------------------------------
# 쿼리 빌더 — B5 발송 대상 산출에서도 그대로 재사용
# ---------------------------------------------------------------------------
def _segment_query(db: Session, criteria: schemas.SegmentCriteria):
    """조건 → Client 쿼리 (축 간 AND, 축 내 IN). 빈 축은 무시(전체).

    project_id·settlement_status는 같은 ProjectClientMap 행에서 함께 평가하는
    EXISTS 1개 — 축을 분리하면 '사업 A 참여' AND '아무 사업에서나 BILLED'가 되어
    다른 사업에서만 청구된 회사가 잘못 포함된다.
    """
    query = db.query(Client)
    if criteria.region:
        query = query.filter(Client.region.in_(criteria.region))
    if criteria.client_type:
        query = query.filter(Client.client_type.in_(criteria.client_type))
    if criteria.contract_status:
        query = query.filter(Client.contract_status.in_(criteria.contract_status))
    if criteria.project_id or criteria.settlement_status:
        map_sub = db.query(ProjectClientMap.map_id).filter(
            ProjectClientMap.client_id == Client.client_id
        )
        if criteria.project_id:
            map_sub = map_sub.filter(ProjectClientMap.project_id.in_(criteria.project_id))
        if criteria.settlement_status:
            map_sub = map_sub.filter(
                ProjectClientMap.settlement_status.in_(criteria.settlement_status)
            )
        query = query.filter(map_sub.exists())
    if criteria.asset_group:
        asset_sub = db.query(Asset.asset_id).filter(
            Asset.client_id == Client.client_id,
            Asset.asset_group.in_(criteria.asset_group),
        )
        query = query.filter(asset_sub.exists())
    return query


def can_receive_map(db: Session, clients: List[Client]) -> dict:
    """고객사별 수신 가능 여부 — {client_id: bool}.

    공통 수신자(tb_report_recipient, sub_id IS NULL) 중 TO 후보(cc_yn != 'Y') 존재
    or main_contact_email 보유. CC 전용 수신자만 있으면 TO 0건으로 실제 발송이
    실패하므로 여기서도 제외 — report_sender.resolve_recipients(sub=None)의
    TO 판정과 동일 기준. B5 발송 가능 대상 선별에서도 재사용.
    """
    ids = [c.client_id for c in clients]
    if not ids:
        return {}
    with_common = {
        cid
        for (cid,) in db.query(ReportRecipient.client_id)
        .filter(
            ReportRecipient.client_id.in_(ids),
            ReportRecipient.sub_id.is_(None),
            func.coalesce(ReportRecipient.cc_yn, "N") != "Y",
        )
        .distinct()
        .all()
    }
    return {
        c.client_id: c.client_id in with_common or bool((c.main_contact_email or "").strip())
        for c in clients
    }


# ---------------------------------------------------------------------------
# criteria 검증·직렬화 헬퍼
# ---------------------------------------------------------------------------
def _validate_criteria(db: Session, criteria: schemas.SegmentCriteria) -> None:
    """criteria 값 검증 — 코드 축은 활성 공통 코드(validate_active_code 재사용),
    project_id는 존재 여부. 미지원 키는 스키마(extra=forbid)가 422 처리."""
    for field, category in CRITERIA_CODE_CATEGORIES.items():
        for value in getattr(criteria, field) or []:
            validate_active_code(db, category, value)
    for project_id in criteria.project_id or []:
        if db.get(Project, project_id) is None:
            raise HTTPException(
                status_code=422,
                detail="존재하지 않는 감축 사업입니다: '{0}'".format(project_id),
            )


def _dump_criteria(criteria: schemas.SegmentCriteria) -> str:
    return json.dumps(criteria.model_dump(exclude_none=True), ensure_ascii=False)


def _row_criteria(row: Segment) -> schemas.SegmentCriteria:
    """저장된 JSON 문자열 → SegmentCriteria (파싱 실패 시 빈 조건)."""
    return schemas.SegmentOut.model_validate(row, from_attributes=True).criteria


def _criteria_summary(criteria: schemas.SegmentCriteria) -> str:
    """감사 로그용 요약 — 축=값 나열 (R2-E6: 조건 요약만, 비밀값 없음)."""
    parts = [
        "{0}={1}".format(field, ",".join(values))
        for field, values in criteria.model_dump(exclude_none=True).items()
        if values
    ]
    return "; ".join(parts) or "(전체)"


def _segment_outs(db: Session, rows: List[Segment]) -> List[schemas.SegmentOut]:
    unames = common.user_name_map(db, [s.manager_id for s in rows])
    return [
        schemas.SegmentOut.model_validate(s, from_attributes=True).model_copy(
            update={"manager_name": unames.get(s.manager_id)}
        )
        for s in rows
    ]


# ---------------------------------------------------------------------------
# 미리보기·facets (조회 — 인증 사용자 전체)
# ---------------------------------------------------------------------------
@router.post("/preview", response_model=schemas.SegmentPreviewResponse)
def preview_segment(
    payload: schemas.SegmentPreviewRequest,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """조건에 맞는 고객사 미리보기 — 발송 전 대상·수신 가능 여부 확인용."""
    rows = _segment_query(db, payload.criteria).order_by(Client.company_name.asc()).all()
    receivable = can_receive_map(db, rows)
    items = [
        schemas.SegmentPreviewItem(
            client_id=c.client_id,
            company_name=c.company_name,
            client_type=c.client_type,
            region=c.region,
            contract_status=c.contract_status,
            can_receive=receivable.get(c.client_id, False),
        )
        for c in rows
    ]
    return schemas.SegmentPreviewResponse(total=len(items), items=items)


@router.get("/facets", response_model=schemas.SegmentFacetsOut)
def segment_facets(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """region 축 선택지 — 고객사 distinct(빈 값 제외, 정렬)."""
    rows = (
        db.query(Client.region)
        .filter(Client.region.isnot(None), Client.region != "")
        .distinct()
        .all()
    )
    return schemas.SegmentFacetsOut(regions=sorted(region for (region,) in rows))


# ---------------------------------------------------------------------------
# CRUD (변경 — master.write)
# ---------------------------------------------------------------------------
@router.get("", response_model=List[schemas.SegmentOut])
def list_segments(
    include_inactive: bool = Query(False, description="soft 삭제(active=N) 포함 여부"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """세그먼트 목록 — 기본은 활성만(soft 삭제 제외)."""
    query = db.query(Segment)
    if not include_inactive:
        query = query.filter(Segment.active == "Y")
    rows = query.order_by(Segment.created_at.desc()).all()
    return _segment_outs(db, rows)


@router.post("", response_model=schemas.SegmentOut, status_code=201)
def create_segment(
    payload: schemas.SegmentIn,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """세그먼트 생성 — criteria 값은 공통 코드·사업 존재 검증 후 JSON 저장."""
    _validate_criteria(db, payload.criteria)
    row = Segment(
        name=payload.name.strip(),
        description=payload.description,
        criteria=_dump_criteria(payload.criteria),
        manager_id=payload.manager_id,
        mail_subject=payload.mail_subject,
        mail_body=payload.mail_body,
        active="Y",
    )
    db.add(row)
    db.flush()
    AuditLogger.log_action(
        db, user.user_id, "SEGMENT_CREATE", target_type="SEGMENT", target_id=row.segment_id,
        new_value="{0} — {1}".format(row.name, _criteria_summary(payload.criteria)),
    )
    db.commit()
    db.refresh(row)
    return _segment_outs(db, [row])[0]


@router.put("/{segment_id}", response_model=schemas.SegmentOut)
def update_segment(
    segment_id: str,
    payload: schemas.SegmentUpdate,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """세그먼트 수정 — 전달된 필드만 반영, criteria 전달 시 재검증.

    soft 삭제(active=N) 세그먼트는 404 — 발송(send_segment)과 동일 톤. 삭제분의
    active=Y 부활은 전용 의도가 아니므로 수정 경로에서는 허용하지 않는다."""
    row = common.get_or_404(db, Segment, segment_id, "세그먼트")
    if row.active != "Y":
        raise HTTPException(status_code=404, detail="세그먼트를 찾을 수 없습니다 (삭제됨)")
    before = "{0} — {1}".format(row.name, _criteria_summary(_row_criteria(row)))

    if payload.criteria is not None:
        _validate_criteria(db, payload.criteria)
        row.criteria = _dump_criteria(payload.criteria)
    if payload.name is not None:
        row.name = payload.name.strip()
    if payload.description is not None:
        row.description = payload.description
    if payload.manager_id is not None:
        row.manager_id = payload.manager_id
    if payload.mail_subject is not None:
        row.mail_subject = payload.mail_subject
    if payload.mail_body is not None:
        row.mail_body = payload.mail_body
    if payload.active is not None:
        row.active = payload.active
    after = "{0} — {1}".format(row.name, _criteria_summary(_row_criteria(row)))

    AuditLogger.log_action(
        db, user.user_id, "SEGMENT_UPDATE", target_type="SEGMENT", target_id=row.segment_id,
        old_value=before, new_value=after,
    )
    db.commit()
    db.refresh(row)
    return _segment_outs(db, [row])[0]


# ---------------------------------------------------------------------------
# 발송 실행 (B5) — tb_segment_send + 고객사별 tb_segment_send_log (변경 — master.write)
# ---------------------------------------------------------------------------
def _load_attachments(
    db: Session, doc_ids: List[str], dropbox_paths: Optional[List[str]] = None
) -> List[tuple]:
    """첨부 선로딩 — 발송 전 1회(팬아웃 전원 공통). 없는 doc_id 404, 유실·총량 초과 422.

    문서함(doc_ids) + 공용 발송자료 Dropbox(dropbox_paths)를 합산 총량으로 검사한다.
    반환: email_service.Attachment 목록 [(filename, bytes, None)].
    """
    attachments = []
    total_bytes = 0
    for doc_id in doc_ids:
        doc = common.get_or_404(db, Document, doc_id, "문서")
        content = storage.read_file(doc.file_url)
        if content is None:
            raise HTTPException(
                status_code=422,
                detail="첨부 문서를 저장소에서 읽을 수 없습니다: '{0}'".format(doc.title),
            )
        total_bytes += len(content)
        if total_bytes > MAX_ATTACHMENT_TOTAL_BYTES:
            raise HTTPException(
                status_code=422,
                detail="첨부 총량이 20MB를 초과합니다. 파일 수를 줄이거나 더 작은 파일을 선택하세요",
            )
        filename = os.path.basename(doc.file_url) or (doc.title or "document")
        attachments.append((filename, content, None))

    # 공용 발송자료 Dropbox 파일(공통) — 반드시 공용 폴더 하위로 제한(confinement),
    # 다운로드 전 size로 doc_ids와 합산 총량 사전검사(OOM 방지).
    if dropbox_paths and not dropbox_storage.is_configured():
        raise HTTPException(status_code=503, detail="Dropbox 연동이 설정되지 않았습니다.")
    public_root = client_folders.public_send_root()
    for raw_path in dropbox_paths or []:
        norm = client_folders.normalize_dropbox_path(raw_path)
        if not client_folders.is_within_folder(public_root, norm):
            raise HTTPException(
                status_code=403,
                detail="공용 발송자료 폴더 밖의 파일은 첨부할 수 없습니다: {0}".format(raw_path),
            )
        size = dropbox_storage.file_size(norm)
        if size is None:
            raise HTTPException(
                status_code=422,
                detail="첨부 파일을 찾을 수 없습니다(폴더이거나 삭제됨): {0}".format(
                    os.path.basename(norm)
                ),
            )
        total_bytes += size
        if total_bytes > MAX_ATTACHMENT_TOTAL_BYTES:
            raise HTTPException(
                status_code=422,
                detail="첨부 총량이 20MB를 초과합니다. 파일 수를 줄이거나 더 작은 파일을 선택하세요",
            )
        content = storage.read_file("dropbox:" + norm)
        if content is None:
            raise HTTPException(
                status_code=422,
                detail="첨부 파일을 저장소에서 읽을 수 없습니다: {0}".format(os.path.basename(norm)),
            )
        attachments.append((os.path.basename(norm) or "file", content, None))
    return attachments


def _resolve_send_templates(
    segment: Optional[Segment], subject: Optional[str], body: Optional[str]
) -> tuple:
    """제목·본문 템플릿 결정 — 요청 오버라이드 → 세그먼트 → 세그먼트 전용 기본값 3단.

    tb_config(report_mail_*) 폴백은 의도적으로 건너뛴다 — 월간 보고서용 템플릿의
    {보고서유형}이 세그먼트 발송 변수에 없어 리터럴로 발송되기 때문.
    빈 문자열은 미지정으로 취급(render_mail 관용구).
    """
    subject_tpl = (
        (subject or "").strip()
        or ((segment.mail_subject or "").strip() if segment else "")
        or DEFAULT_SEGMENT_MAIL_SUBJECT
    )
    body_tpl = (
        (body or "").strip()
        or ((segment.mail_body or "").strip() if segment else "")
        or DEFAULT_SEGMENT_MAIL_BODY
    )
    return subject_tpl, body_tpl


def _execute_send(
    db: Session,
    user: User,
    criteria: schemas.SegmentCriteria,
    payload: schemas.SegmentSendRequest,
    segment: Optional[Segment],
) -> schemas.SegmentSendResponse:
    """발송 실행 공통 코어 — 즉석/저장 세그먼트 발송이 공유.

    - Gmail 미설정 503 즉중단 (SegmentSend 미생성 — 상태 무변경, batch.py 관용구)
    - 첨부 선로딩 1회 → 대상 산출 → SegmentSend 스냅샷 커밋 → 고객사 루프(건별 실패 격리)
    - 고객사별: 수신자 해석(sub=None 공통분) → TO 0건 FAIL(수신자 없음) → send_mail →
      SUCCESS/FAIL 로그 + 성공 시 활동 이력 EMAIL "[자동]" 적재 → 건별 commit
      (batch.py 관용구 — 중간 실패로 프로세스가 끊겨도 기왕 발송분 이력 보존)
    - 감사 로그는 카운트 요약만 (R2-E6 — 수신자 이메일 미기록)
    """
    if not email_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "이메일 발송 기능이 아직 설정되지 않았습니다. "
                "GMAIL_SENDER / GMAIL_APP_PASSWORD 환경변수를 설정한 뒤 다시 시도하세요 (CR-2). "
                "발송 이력은 생성되지 않았습니다."
            ),
        )

    if not payload.doc_ids and not (payload.dropbox_paths or []):
        raise HTTPException(
            status_code=422,
            detail="문서함 파일 또는 공용 Dropbox 파일을 최소 1개 선택하세요",
        )
    attachments = _load_attachments(db, payload.doc_ids, payload.dropbox_paths)
    targets = _segment_query(db, criteria).order_by(Client.company_name.asc()).all()
    subject_tpl, body_tpl = _resolve_send_templates(segment, payload.subject, payload.body)

    send = SegmentSend(
        segment_id=segment.segment_id if segment else None,
        criteria_snapshot=_dump_criteria(criteria),
        doc_ids=json.dumps(payload.doc_ids, ensure_ascii=False),
        subject=subject_tpl[:200],  # tb_segment_send.subject String(200)
        body=body_tpl,
        target_count=len(targets),
        sent_by=user.user_id,
    )
    db.add(send)
    db.commit()  # 실행 이력 선확정 — 이후 루프는 건별 commit(중간 실패 시에도 이력 보존)

    # 치환 변수 공통분 — 연·월은 발송 시점 KST 벽시계 (common.now_kst 규약)
    now_kst = common.now_kst()
    manager_ids = {c.manager_id for c in targets if c.manager_id}
    managers = (
        {u.user_id: u for u in db.query(User).filter(User.user_id.in_(manager_ids)).all()}
        if manager_ids
        else {}
    )

    sent = failed = 0
    details = []
    for target in targets:
        to, cc = resolve_recipients(db, target, sub=None)
        if not to:
            failed += 1
            reason = "수신자 없음 — 공통 수신자 또는 주 담당자 이메일을 확인하세요 (R2-B5)"
            db.add(
                SegmentSendLog(
                    send_id=send.send_id, client_id=target.client_id,
                    recipients=None, channel="EMAIL", result="FAIL", reason=reason,
                )
            )
            send.failed_count = failed
            db.commit()  # 건별 확정 — 중간 실패 시에도 기왕 로그 보존
            details.append(
                schemas.SegmentSendDetail(
                    client_id=target.client_id, client_name=target.company_name,
                    result="FAIL", reason=reason,
                )
            )
            continue

        manager = managers.get(target.manager_id)
        variables = {
            "고객사명": target.company_name or "",
            "연도": str(now_kst.year),
            "월": str(now_kst.month),
            "담당자명": (manager.name if manager else None) or "",
        }
        subject = render_template(subject_tpl, variables)
        body = render_template(body_tpl, variables)
        recipients_snapshot = json.dumps({"to": to, "cc": cc}, ensure_ascii=False)

        try:
            email_service.send_mail(
                to=to,
                subject=subject,
                body=body,
                cc=cc or None,
                attachments=attachments,
                reply_to=(manager.email if manager else None) or user.email,
            )
        except Exception as exc:  # 건별 실패 격리 — 전체 중단 금지 (batch.py 관용구)
            failed += 1
            reason = str(exc)[:300]  # tb_segment_send_log.reason String(300)
            db.add(
                SegmentSendLog(
                    send_id=send.send_id, client_id=target.client_id,
                    recipients=recipients_snapshot, channel="EMAIL",
                    result="FAIL", reason=reason,
                )
            )
            send.failed_count = failed
            db.commit()  # 건별 확정 — 중간 실패 시에도 기왕 로그 보존
            details.append(
                schemas.SegmentSendDetail(
                    client_id=target.client_id, client_name=target.company_name,
                    result="FAIL", reason=reason,
                )
            )
            continue

        sent += 1
        db.add(
            SegmentSendLog(
                send_id=send.send_id, client_id=target.client_id,
                recipients=recipients_snapshot, channel="EMAIL", result="SUCCESS",
            )
        )
        # 활동 이력 EMAIL 자동 적재 (§9-3 — report_sender와 동일 관용구)
        db.add(
            ActivityHistory(
                client_id=target.client_id,
                manager_id=user.user_id,
                created_by=user.user_id,
                activity_date=now_kst,  # 저장값=KST 벽시계 규약 (created_at 계열은 UTC 유지)
                activity_type="EMAIL",
                title="{0} 세그먼트 메일 발송: {1}".format(common.AUTO_PREFIX, subject)[:200],
                content="수신자: {0}".format(", ".join(to + cc)),
            )
        )
        send.sent_count = sent
        db.commit()  # 건별 확정 — 발송 성공 직후 로그·활동이력·카운트 저장
        details.append(
            schemas.SegmentSendDetail(
                client_id=target.client_id, client_name=target.company_name,
                result="SUCCESS",
            )
        )

    # 감사 로그 — 카운트·조건 요약만 (R2-E6: 수신자 이메일 미기록)
    # 첨부 요약: 문서함 수 + 공용 Dropbox 파일명(basename만, R2-E6) — 이력 재현/감사용
    dbx_names = [
        os.path.basename(client_folders.normalize_dropbox_path(p))
        for p in (payload.dropbox_paths or [])
    ]
    attach_summary = "docs={0}, dropbox=[{1}]".format(
        len(payload.doc_ids), ", ".join(dbx_names)
    )
    AuditLogger.log_action(
        db, user.user_id, "SEGMENT_SEND", target_type="SEGMENT_SEND", target_id=send.send_id,
        new_value="targets={0}, sent={1}, failed={2}, {3} — {4}".format(
            len(targets), sent, failed, attach_summary, _criteria_summary(criteria)
        ),
    )
    db.commit()
    return schemas.SegmentSendResponse(
        send_id=send.send_id,
        target_count=len(targets),
        sent_count=sent,
        failed_count=failed,
        details=details,
    )


@router.post("/send", response_model=schemas.SegmentSendResponse)
def send_adhoc(
    payload: schemas.SegmentSendRequest,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """즉석 발송 — 세그먼트 저장 없이 criteria로 바로 발송 (criteria 필수)."""
    if payload.criteria is None:
        raise HTTPException(status_code=422, detail="즉석 발송에는 criteria가 필요합니다")
    _validate_criteria(db, payload.criteria)
    return _execute_send(db, user, payload.criteria, payload, segment=None)


@router.post("/{segment_id}/send", response_model=schemas.SegmentSendResponse)
def send_segment(
    segment_id: str,
    payload: schemas.SegmentSendRequest,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """저장 세그먼트 발송 — criteria는 저장분 사용(요청 criteria 무시),
    subject/body 미지정 시 세그먼트 mail_subject/mail_body 오버라이드 반영.
    soft 삭제(active=N) 세그먼트는 404 — 목록에서 안 보이는 대상으로 발송 방지."""
    row = common.get_or_404(db, Segment, segment_id, "세그먼트")
    if row.active != "Y":
        raise HTTPException(status_code=404, detail="세그먼트를 찾을 수 없습니다 (삭제됨)")
    return _execute_send(db, user, _row_criteria(row), payload, segment=row)


# ---------------------------------------------------------------------------
# 발송 이력 조회 (B5 — 인증 사용자 전체)
# ---------------------------------------------------------------------------
@router.get("/sends", response_model=List[schemas.SegmentSendOut])
def list_sends(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """발송 실행 이력 목록 — 최신순."""
    rows = db.query(SegmentSend).order_by(SegmentSend.created_at.desc()).all()
    unames = common.user_name_map(db, [r.sent_by for r in rows])
    return [
        schemas.SegmentSendOut.model_validate(r, from_attributes=True).model_copy(
            update={"sent_by_name": unames.get(r.sent_by)}
        )
        for r in rows
    ]


@router.get("/sends/{send_id}", response_model=schemas.SegmentSendDetailOut)
def get_send(
    send_id: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """발송 실행 이력 상세 — 고객사별 로그 포함."""
    row = common.get_or_404(db, SegmentSend, send_id, "발송 이력")
    logs = (
        db.query(SegmentSendLog)
        .filter(SegmentSendLog.send_id == send_id)
        .order_by(SegmentSendLog.created_at.asc())
        .all()
    )
    cnames = {
        cid: name
        for cid, name in db.query(Client.client_id, Client.company_name)
        .filter(Client.client_id.in_({l.client_id for l in logs}))
        .all()
    } if logs else {}
    unames = common.user_name_map(db, [row.sent_by])
    return schemas.SegmentSendDetailOut.model_validate(
        row, from_attributes=True
    ).model_copy(
        update={
            "sent_by_name": unames.get(row.sent_by),
            "logs": [
                schemas.SegmentSendLogOut.model_validate(l, from_attributes=True).model_copy(
                    update={"client_name": cnames.get(l.client_id)}
                )
                for l in logs
            ],
        }
    )


@router.delete("/{segment_id}", status_code=204)
def delete_segment(
    segment_id: str,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """세그먼트 삭제 — soft(active=N). 발송 이력(tb_segment_send) 참조 보존."""
    row = common.get_or_404(db, Segment, segment_id, "세그먼트")
    row.active = "N"
    AuditLogger.log_action(
        db, user.user_id, "SEGMENT_DELETE", target_type="SEGMENT", target_id=row.segment_id,
        old_value=row.name,
    )
    db.commit()
    return None
