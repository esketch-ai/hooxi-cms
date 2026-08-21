"""외부 포털 계정 온보딩(provision) — Phase 4 INC-6 / 부록 N.8 D3(격리).

내부 users 관리(schemas 역할 정규식 ^(ADMIN|MANAGER|STAFF)$)와 완전히 분리된 전용 경로.
외부역할(PARTNER/INVESTOR) 부여는 오직 이 라우터에서만 일어난다 — 내부 users API로는
정규식으로 원천 차단되어 외부역할을 만들 수 없다(격리 D3 불변식).

- 인가: 내부 MANAGER 이상(require_role은 get_current_user 기반 → 외부역할은 원천 403).
- 매직링크: create_magic_token 재사용, FRONTEND 기준 링크 '문자열'을 항상 반환(수동 복사 폴백).
  발송은 INC-10 이메일(Gmail)을 주 채널로 best-effort 자동 전송하고, 카카오 알림톡은 설정 시
  폴백으로만 시도한다(이메일 성공 시 중복 발송 안 함). 감사에는 발급 '사실'만 남기고
  토큰 원문·링크는 절대 기록하지 않는다(R2-E6).
- 카카오 브릿지(최소): kakao_contact_id가 주어지면 승인된 KakaoContact.client_id로 보강.
  kakao.py 승인 로직 자체는 건드리지 않는다(회귀 격리).
"""

import html
import logging
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import schemas
from auth import EXTERNAL_ROLES, FRONTEND_ORIGIN, create_magic_token, require_role
from models import ActivityHistory, Buyer, Client, KakaoContact, User, get_db
from routers import common
from services import email_service, kakao_service
from services.audit_logger import AuditLogger
from services.integration_config import resolve as resolve_integration

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/external-accounts", tags=["external-accounts"])


def _issue_magic(user: User) -> Tuple[str, str]:
    """매직 토큰 1회 발급 → (표시용 magic_link, 알림톡 버튼용 절대 링크).

    같은 토큰을 화면 복사와 발송에 함께 써 불일치를 막는다. 표시용은 현행대로 FRONTEND
    기준(Dev에선 상대경로일 수 있음), 알림톡 버튼은 절대 URL 필수라 APP_BASE_URL 우선.
    토큰은 반환값에만 담고 감사엔 남기지 않는다(R2-E6).
    """
    token = create_magic_token(user)
    path = "/portal/login?token={0}".format(token)
    magic_link = "{0}{1}".format(FRONTEND_ORIGIN, path)
    abs_link = "{0}{1}".format(kakao_service.app_base_url() or FRONTEND_ORIGIN, path)
    return magic_link, abs_link


def _send_portal_invite(user: User, abs_link: str) -> str:
    """포털 초대 알림톡 best-effort 발송 → 결과 문자열. 예외를 밖으로 던지지 않는다.

    반환: SENT / FAILED / NOT_CONFIGURED / NO_TEMPLATE / NO_PHONE.
    발송 실패가 계정 발급을 깨지 않도록 모든 실패를 결과 문자열로만 흡수한다.
    """
    if not kakao_service.is_configured_alimtalk():
        return "NOT_CONFIGURED"
    template = resolve_integration("KAKAO_TEMPLATE_PORTAL_INVITE")
    if not template:
        return "NO_TEMPLATE"
    if not user.phone:
        return "NO_PHONE"
    try:
        kakao_service.send_alimtalk(
            to=user.phone,
            template_code=template,
            variables={"이름": user.name or "고객님"},
            buttons=[
                {
                    "buttonType": "WL",
                    "buttonName": "포털 열기",
                    "linkMo": abs_link,
                    "linkPc": abs_link,
                }
            ],
        )
        return "SENT"
    except Exception as exc:
        # R2-E6: 토큰·링크·수신번호가 새지 않도록 예외 '유형명'만 기록(메시지 본문 미기록)
        logger.warning("포털 초대 알림톡 발송 실패: %s", type(exc).__name__)
        return "FAILED"


def _send_portal_invite_email(user: User, abs_link: str) -> str:
    """포털 초대 이메일 best-effort 발송(Gmail) → 결과 문자열. 예외를 밖으로 던지지 않는다.

    반환: SENT / FAILED / NOT_CONFIGURED. 수신자는 항상 존재하는 user.email.
    발송 실패가 계정 발급을 깨지 않도록 모든 실패를 결과 문자열로만 흡수한다(R2-E6).
    """
    if not email_service.is_configured():
        return "NOT_CONFIGURED"
    name = html.escape(user.name or "고객님")  # HTML 본문 주입 방지(담당자 입력 이름 이스케이프)
    subject = "[후시 파트너] 포털 접속 링크 안내"
    body = (
        "<div style=\"font-family:sans-serif;font-size:14px;line-height:1.7;color:#222\">"
        "<p>{name}님, 안녕하세요.</p>"
        "<p>후시 파트너 고객 포털 접속 링크를 안내드립니다. "
        "아래 버튼을 눌러 로그인해 주세요.</p>"
        "<p style=\"margin:24px 0\">"
        "<a href=\"{link}\" style=\"display:inline-block;padding:12px 24px;"
        "background:#2563eb;color:#fff;text-decoration:none;border-radius:6px\">"
        "포털 접속하기</a></p>"
        "<p style=\"font-size:12px;color:#666\">버튼이 열리지 않으면 아래 주소를 복사해 "
        "브라우저에 붙여넣어 주세요.<br><a href=\"{link}\">{link}</a></p>"
        "<p style=\"font-size:12px;color:#666\">본 링크는 발송 시점부터 <b>24시간</b> 동안 유효합니다.</p>"
        "</div>"
    ).format(name=name, link=abs_link)
    try:
        email_service.send_mail(to=[user.email], subject=subject, body=body, html=True)
        return "SENT"
    except Exception as exc:
        # R2-E6: 토큰·링크·수신 주소가 새지 않도록 예외 '유형명'만 기록(본문 미로깅)
        logger.warning("포털 초대 이메일 발송 실패: %s", type(exc).__name__)
        return "FAILED"


def _deliver_magic_link(user: User, abs_link: str) -> str:
    """매직링크 발송 오케스트레이션 — 이메일(주) → 카카오(폴백). 정규화 결과 문자열.

    반환: EMAIL_SENT / KAKAO_SENT / EMAIL_FAILED / KAKAO_FAILED / NOT_CONFIGURED.
    이메일이 성공하면 카카오는 시도하지 않는다(중복 발송 방지). 어떤 채널도 설정/발송
    불가하면 NOT_CONFIGURED — 이때도 magic_link 문자열 폴백으로 수동 전달이 가능하다.
    전 과정을 try로 감싸 설정 조회(resolve) 예외까지 흡수한다(best-effort 완전 격리).
    """
    try:
        # _send_portal_invite_email 자체가 미설정 시 NOT_CONFIGURED를 반환(is_configured 중복 제거)
        email_status = _send_portal_invite_email(user, abs_link)  # SENT/FAILED/NOT_CONFIGURED
        if email_status == "SENT":
            return "EMAIL_SENT"
        kakao_status = _send_portal_invite(user, abs_link)  # 기존 카카오 헬퍼(설정 시 발송)
        if kakao_status == "SENT":
            return "KAKAO_SENT"
        if email_status == "FAILED":
            return "EMAIL_FAILED"
        if kakao_status == "FAILED":
            return "KAKAO_FAILED"
        return "NOT_CONFIGURED"  # 어떤 채널도 발송 불가 — magic_link 수동 전달 폴백
    except Exception as exc:
        # 설정 조회 등 예상 밖 오류도 발급을 깨지 않는다(토큰·링크 미로깅, 유형명만)
        logger.warning("포털 초대 발송 오케스트레이션 오류: %s", type(exc).__name__)
        return "NOT_CONFIGURED"


def _log_portal_invite_activity(
    db: Session, manager: User, target: User, delivery: str, resend: bool
) -> None:
    """포털 초대 링크 발송을 영업활동 이력에 자동 적재(고객사·투자사별 발송 관리).

    PARTNER는 해당 고객사 이력으로(상세 활동 이력 탭에 노출), INVESTOR는 고객사 미지정
    이력으로 매수자명을 제목에 남긴다. 매직링크 원문은 절대 기록하지 않는다(R2-E6 —
    링크는 로그인 수단). 실패해도 발급 자체에는 영향 없음(best-effort).
    """
    try:
        org = ""
        if target.role == "PARTNER" and target.client_id:
            c = db.get(Client, target.client_id)
            org = c.company_name if c else ""
        elif target.role == "INVESTOR" and target.buyer_id:
            b = db.get(Buyer, target.buyer_id)
            org = b.name if b else ""
        action = "재발급" if resend else "발급"
        db.add(
            ActivityHistory(
                client_id=target.client_id,  # INVESTOR는 None(미지정 이력)
                manager_id=manager.user_id,
                created_by=manager.user_id,
                activity_date=common.now_kst(),
                activity_type="PORTAL",
                title="{0} 포털 초대 링크 {1} — {2}".format(common.AUTO_PREFIX, action, org or target.email),
                content="역할 {0} · 수신 {1} · 발송 {2}".format(
                    target.role, target.email, delivery
                ),
            )
        )
        db.commit()
    except Exception:
        db.rollback()


def _account_out(
    user: User,
    magic_link: Optional[str] = None,
    delivery: Optional[str] = None,
) -> schemas.ExternalAccountOut:
    out = schemas.ExternalAccountOut.model_validate(user, from_attributes=True)
    return out.model_copy(update={"magic_link": magic_link, "delivery": delivery})


@router.post("", response_model=schemas.ExternalAccountOut, status_code=201)
def create_external_account(
    payload: schemas.ExternalAccountIn,
    manager: User = Depends(require_role("MANAGER")),
    db: Session = Depends(get_db),
):
    """외부 포털 계정 provision — 즉시 ACTIVE + 매직링크 발급(문자열 반환).

    - PARTNER: client_id 필수(Client 존재·TRANSPORT). kakao_contact_id 주어지면 그
      승인 연락처의 client_id로 보강(명시 client_id 우선).
    - INVESTOR: buyer_id 필수(Buyer 존재).
    - 이메일 중복 허용: 대표·임원이 같은 이메일로 여러 고객사/투자사 포털 계정을 요청하는
      현실 반영. 같은 (이메일×역할×조직)의 활성 계정이 이미 있으면 새로 만들지 않고
      매직링크 재발급으로 처리한다(중복 행 방지). 내부 계정과 같은 이메일도 허용 —
      내부 로그인(JIT·dev-login)은 내부 역할만 조회하므로 충돌 없음.
    """
    email = payload.email.strip().lower()

    client_id: Optional[str] = None
    buyer_id: Optional[str] = None
    phone: Optional[str] = (payload.phone or "").strip() or None

    if payload.role == "PARTNER":
        client_id = payload.client_id
        # 카카오 브릿지(최소): 승인 연락처의 client_id로 보강 — 명시 client_id가 우선
        if payload.kakao_contact_id:
            contact = common.get_or_404(
                db, KakaoContact, payload.kakao_contact_id, "카카오 연락처"
            )
            client_id = client_id or contact.client_id
            # 전화번호 미지정 시 승인 연락처 번호로 보완(알림톡 발송 대상) — 명시 phone 우선
            if not phone and contact.status == "APPROVED" and contact.phone:
                phone = contact.phone
        if not client_id:
            raise HTTPException(
                status_code=422, detail="PARTNER 계정에는 운수사(client_id)가 필요합니다"
            )
        client = common.get_or_404(db, Client, client_id, "고객사")
        if client.client_type != "TRANSPORT":
            raise HTTPException(
                status_code=422,
                detail="PARTNER 계정은 운수사(TRANSPORT) 고객사에만 연결할 수 있습니다",
            )
    else:  # INVESTOR
        if not payload.buyer_id:
            raise HTTPException(
                status_code=422, detail="INVESTOR 계정에는 매수자(buyer_id)가 필요합니다"
            )
        common.get_or_404(db, Buyer, payload.buyer_id, "매수자")
        buyer_id = payload.buyer_id

    # 같은 (이메일×역할×조직) 계정이 이미 있으면 — 중복 생성 대신 그 계정으로 재발급
    existing = (
        db.query(User)
        .filter(
            User.email == email,
            User.role == payload.role,
            User.client_id == client_id if payload.role == "PARTNER" else User.buyer_id == buyer_id,
        )
        .first()
    )
    if existing is not None:
        if existing.status != "ACTIVE":
            existing.status = "ACTIVE"  # 비활성이었다면 재활성 후 발급(재초대)
        if phone and not existing.phone:
            existing.phone = phone
        AuditLogger.external_account_resend(db, manager.user_id, existing.user_id)
        db.commit()
        db.refresh(existing)
        magic_link, abs_link = _issue_magic(existing)
        delivery = _deliver_magic_link(existing, abs_link)
        _log_portal_invite_activity(db, manager, existing, delivery, resend=True)
        return _account_out(existing, magic_link, delivery)

    user = User(
        email=email,
        name=payload.name or email.split("@")[0],
        role=payload.role,
        status="ACTIVE",
        auth_provider="PORTAL",
        token_version=0,
        client_id=client_id,
        buyer_id=buyer_id,
        phone=phone,
    )
    db.add(user)
    db.flush()
    AuditLogger.external_account_create(db, manager.user_id, user.user_id, payload.role)
    # 계정을 먼저 커밋한 뒤 발송한다 — 트랜잭션 내 HTTP I/O(락 유지)·"발송 후 롤백" 엣지 제거
    db.commit()
    db.refresh(user)
    magic_link, abs_link = _issue_magic(user)  # 토큰 1회 발급(원문 미기록) → 표시·발송 공용
    delivery = _deliver_magic_link(user, abs_link)  # 이메일(주)→카카오(폴백), best-effort
    _log_portal_invite_activity(db, manager, user, delivery, resend=False)
    return _account_out(user, magic_link, delivery)


@router.post("/{user_id}/resend-link", response_model=schemas.ExternalAccountOut)
def resend_magic_link(
    user_id: str,
    manager: User = Depends(require_role("MANAGER")),
    db: Session = Depends(get_db),
):
    """외부 계정 매직링크 재발급 — 활성 외부역할 계정만."""
    user = common.get_or_404(db, User, user_id, "사용자")
    if user.role not in EXTERNAL_ROLES:
        raise HTTPException(status_code=404, detail="외부 포털 계정이 아닙니다")
    if user.status != "ACTIVE":
        raise HTTPException(
            status_code=409, detail="활성(ACTIVE) 상태의 외부 계정만 링크를 재발급할 수 있습니다"
        )
    AuditLogger.external_account_resend(db, manager.user_id, user.user_id)
    db.commit()  # 감사 확정 후 발송 — 트랜잭션 밖에서 best-effort 재발송
    magic_link, abs_link = _issue_magic(user)
    delivery = _deliver_magic_link(user, abs_link)  # 이메일(주)→카카오(폴백), best-effort 재발송
    _log_portal_invite_activity(db, manager, user, delivery, resend=True)
    return _account_out(user, magic_link, delivery)


@router.get("", response_model=List[schemas.ExternalAccountOut])
def list_external_accounts(
    _: User = Depends(require_role("MANAGER")),
    db: Session = Depends(get_db),
):
    """외부역할 계정 목록 — role·연결 client/buyer·status. magic_link는 미포함(None)."""
    users = (
        db.query(User)
        .filter(User.role.in_(sorted(EXTERNAL_ROLES)))
        .order_by(User.created_at.desc())
        .all()
    )
    return [_account_out(u) for u in users]


@router.delete("/{user_id}", response_model=schemas.ExternalAccountOut)
def deactivate_external_account(
    user_id: str,
    manager: User = Depends(require_role("MANAGER")),
    db: Session = Depends(get_db),
):
    """외부 계정 비활성(삭제 대신 INACTIVE 권장) — token_version 증가로 발급 토큰 즉시 무효화(C2)."""
    user = common.get_or_404(db, User, user_id, "사용자")
    if user.role not in EXTERNAL_ROLES:
        raise HTTPException(status_code=404, detail="외부 포털 계정이 아닙니다")
    if user.status == "INACTIVE":
        raise HTTPException(status_code=409, detail="이미 비활성화된 계정입니다")
    old_status = user.status
    user.status = "INACTIVE"
    user.token_version = (user.token_version or 0) + 1
    AuditLogger.external_account_deactivate(db, manager.user_id, user.user_id, old_status)
    db.commit()
    db.refresh(user)
    return _account_out(user)


@router.get("/{user_id}/preview", response_model=schemas.ExternalAccountPreview)
def preview_external_account(
    user_id: str,
    manager: User = Depends(require_role("MANAGER")),
    db: Session = Depends(get_db),
):
    """발급 전 미리보기 — 이 외부 계정이 포털에서 보게 될 내용을 관리자가 검증(read-only).

    포털 라우트 함수(자기 스코프 필터 내장)를 그대로 호출해 실제 포털 응답과 1:1 동일함을
    보장한다(격리는 유지 — 관리자 세션·토큰 전환 없음, 내부 API로만 조회).
    감사 로그 PORTAL_PREVIEW(값 미기록 — R2-E6).
    """
    target = db.get(User, user_id)
    if target is None or target.role not in EXTERNAL_ROLES:
        raise HTTPException(status_code=404, detail="외부 계정을 찾을 수 없습니다")

    from routers import portal as portal_routes

    org_name = None
    if target.role == "PARTNER" and target.client_id:
        c = db.get(Client, target.client_id)
        org_name = c.company_name if c else None
    elif target.role == "INVESTOR" and target.buyer_id:
        b = db.get(Buyer, target.buyer_id)
        org_name = b.name if b else None

    warnings = []
    if target.role == "PARTNER" and not target.client_id:
        warnings.append("연결된 고객사가 없어 포털에 아무것도 표시되지 않습니다")
    if target.role == "INVESTOR" and not target.buyer_id:
        warnings.append("연결된 매수자가 없어 포털에 아무것도 표시되지 않습니다")
    if target.status != "ACTIVE":
        warnings.append("비활성 계정 — 링크를 발급해도 로그인할 수 없습니다")

    projects = portal_routes.list_projects(user=target, db=db)
    fleet = reports = settlements = []
    if target.role == "PARTNER" and target.client_id:
        fleet = portal_routes.portal_fleet_status(user=target, db=db)
        reports = portal_routes.portal_reports(user=target, db=db)
        settlements = portal_routes.portal_settlements(user=target, db=db)

    AuditLogger.log_action(
        db, manager.user_id, "PORTAL_PREVIEW",
        target_type="USER", target_id=user_id, new_value=target.role,
    )
    db.commit()
    return schemas.ExternalAccountPreview(
        user_id=target.user_id, name=target.name, email=target.email,
        role=target.role, status=target.status, org_name=org_name,
        projects=projects, fleet_status=fleet, reports=reports,
        settlements=settlements, warnings=warnings,
    )
