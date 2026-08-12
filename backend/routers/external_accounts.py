"""외부 포털 계정 온보딩(provision) — Phase 4 INC-6 / 부록 N.8 D3(격리).

내부 users 관리(schemas 역할 정규식 ^(ADMIN|MANAGER|STAFF)$)와 완전히 분리된 전용 경로.
외부역할(PARTNER/INVESTOR) 부여는 오직 이 라우터에서만 일어난다 — 내부 users API로는
정규식으로 원천 차단되어 외부역할을 만들 수 없다(격리 D3 불변식).

- 인가: 내부 MANAGER 이상(require_role은 get_current_user 기반 → 외부역할은 원천 403).
- 매직링크: create_magic_token 재사용, FRONTEND 기준 링크 '문자열'만 반환(이메일 자동발송은
  이번 범위 밖 — staff가 전달). 감사에는 발급 '사실'만 남기고 토큰 원문은 절대 기록하지 않는다(R2-E6).
- 카카오 브릿지(최소): kakao_contact_id가 주어지면 승인된 KakaoContact.client_id로 보강.
  kakao.py 승인 로직 자체는 건드리지 않는다(회귀 격리).
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import schemas
from auth import EXTERNAL_ROLES, FRONTEND_ORIGIN, create_magic_token, require_role
from models import Buyer, Client, KakaoContact, User, get_db
from routers import common
from services.audit_logger import AuditLogger

router = APIRouter(prefix="/external-accounts", tags=["external-accounts"])


def _magic_link(user: User) -> str:
    """매직링크 문자열 — FRONTEND 기준 경로. 토큰은 반환값에만 담고 감사엔 남기지 않는다."""
    token = create_magic_token(user)
    return "{0}/portal/login?token={1}".format(FRONTEND_ORIGIN, token)


def _account_out(user: User, magic_link: Optional[str] = None) -> schemas.ExternalAccountOut:
    out = schemas.ExternalAccountOut.model_validate(user, from_attributes=True)
    return out.model_copy(update={"magic_link": magic_link})


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
    - 이메일 중복 409. 역할별 필수 필드 누락 422.
    """
    email = payload.email.strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="이미 등록된 이메일입니다")

    client_id: Optional[str] = None
    buyer_id: Optional[str] = None

    if payload.role == "PARTNER":
        client_id = payload.client_id
        # 카카오 브릿지(최소): 승인 연락처의 client_id로 보강 — 명시 client_id가 우선
        if payload.kakao_contact_id:
            contact = common.get_or_404(
                db, KakaoContact, payload.kakao_contact_id, "카카오 연락처"
            )
            client_id = client_id or contact.client_id
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

    user = User(
        email=email,
        name=payload.name or email.split("@")[0],
        role=payload.role,
        status="ACTIVE",
        auth_provider="PORTAL",
        token_version=0,
        client_id=client_id,
        buyer_id=buyer_id,
    )
    db.add(user)
    db.flush()
    AuditLogger.external_account_create(db, manager.user_id, user.user_id, payload.role)
    link = _magic_link(user)  # 감사 커밋 전에 토큰만 발급(원문 미기록)
    db.commit()
    db.refresh(user)
    return _account_out(user, link)


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
    link = _magic_link(user)
    AuditLogger.external_account_resend(db, manager.user_id, user.user_id)
    db.commit()
    return _account_out(user, link)


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
