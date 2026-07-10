"""자산 및 연동 현황 — SCR-04 (P2).

- 목록: FilterBar(대분류·관제 연동·인증 방식·고객사·검색) + 페이지네이션
- 인증정보(auth_value)는 AES-256-GCM 암호화 저장 — 응답에 평문 절대 미포함
  (has_credentials·auth_type만 노출)
- reveal-auth: 일시 복호화 평문 반환 — tb_audit_log 기록 필수 (§10.1)
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_permission, require_role
from models import Asset, Client, ProjectClientMap, User, get_db, utcnow
from routers import common
from services import crypto
from services.audit_logger import AuditLogger

router = APIRouter(prefix="/assets", tags=["assets"])

# 인증정보 외 일반 필드 — 등록/수정 공용
_ASSET_FIELDS = [
    "client_id", "asset_group", "asset_type", "quantity", "main_spec",
    "telemetry_yn", "location_info", "status", "agency_name", "site_url",
    "auth_type", "login_id", "usage_purpose",
]


def _store_auth_value(asset: Asset, auth_type: Optional[str], auth_value: Optional[str]):
    """평문 인증정보를 AES-256-GCM 암호화해 auth_type에 맞는 컬럼에 저장.

    - 빈 문자열: 인증정보 삭제
    - auth_type=NONE인데 값이 오면 422
    - 키 미설정 시 crypto.encrypt가 503 (다른 필드 변경은 auth_value 미전달 시 정상)
    """
    if not auth_value:
        asset.login_password = None
        asset.api_token = None
        return
    if (auth_type or "NONE") == "NONE":
        raise HTTPException(
            status_code=422, detail="인증 방식이 NONE인 자산에는 인증정보를 저장할 수 없습니다"
        )
    encrypted = crypto.encrypt(auth_value)
    if auth_type == "ID_PW":
        asset.login_password = encrypted
        asset.api_token = None
    else:  # API_KEY
        asset.api_token = encrypted
        asset.login_password = None


def _asset_out(db: Session, asset: Asset) -> schemas.AssetListItem:
    cnames = common.client_name_map(db, [asset.client_id])
    out = schemas.AssetListItem.model_validate(asset, from_attributes=True)
    return out.model_copy(
        update={
            "client_name": cnames.get(asset.client_id),
            "has_credentials": bool(asset.login_password or asset.api_token),
        }
    )


@router.get("", response_model=schemas.AssetListResponse)
def list_assets(
    asset_category: Optional[str] = Query(None, description="대분류 MOBILITY/FACILITY"),
    monitoring_yn: Optional[str] = Query(None, description="관제 연동 Y/N"),
    auth_method: Optional[str] = Query(None, description="인증 방식 API_KEY/ID_PW/NONE"),
    credentials_only: bool = Query(False, description="로그인 계정 보유 자산만 (계정 관리 뷰)"),
    client_id: Optional[str] = Query(None, description="고객사"),
    search: Optional[str] = Query(None, description="고객사명·자산 분류·제원·대상 기관 검색"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """자산 목록 (SCR-04) — 인증정보 값은 절대 미포함(has_credentials·auth_type만)."""
    query = db.query(Asset)
    if asset_category:
        query = query.filter(Asset.asset_group == asset_category)
    if monitoring_yn:
        query = query.filter(Asset.telemetry_yn == monitoring_yn)
    if auth_method:
        query = query.filter(Asset.auth_type == auth_method)
    if credentials_only:
        # 계정 관리 뷰 — 고객 제공 로그인 계정이 있는 자산만
        query = query.filter(Asset.auth_type.isnot(None), Asset.auth_type != "NONE")
    if client_id:
        query = query.filter(Asset.client_id == client_id)
    if search:
        keyword = "%{0}%".format(search.strip())
        matched_clients = [
            cid for (cid,) in
            db.query(Client.client_id).filter(Client.company_name.ilike(keyword)).all()
        ]
        conditions = [
            Asset.asset_type.ilike(keyword),
            Asset.main_spec.ilike(keyword),
            Asset.agency_name.ilike(keyword),
            Asset.location_info.ilike(keyword),
        ]
        if matched_clients:
            conditions.append(Asset.client_id.in_(matched_clients))
        query = query.filter(or_(*conditions))

    total = query.count()
    rows = (
        query.order_by(Asset.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    cnames = common.client_name_map(db, [a.client_id for a in rows])
    items = [
        schemas.AssetListItem.model_validate(a, from_attributes=True).model_copy(
            update={
                "client_name": cnames.get(a.client_id),
                "has_credentials": bool(a.login_password or a.api_token),
            }
        )
        for a in rows
    ]
    return schemas.AssetListResponse(items=items, total=total)


@router.post("", response_model=schemas.AssetListItem, status_code=201)
def create_asset(
    payload: schemas.AssetCreate,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """자산 등록 (SCR-04) — auth_value는 AES-256-GCM 암호화 후 저장."""
    common.get_or_404(db, Client, payload.client_id, "고객사")
    asset = Asset(**{f: getattr(payload, f) for f in _ASSET_FIELDS})
    _store_auth_value(asset, payload.auth_type, payload.auth_value)
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return _asset_out(db, asset)


@router.get("/{asset_id}", response_model=schemas.AssetListItem)
def get_asset(
    asset_id: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """자산 상세 — 인증정보 값 미포함(reveal-auth로만 일시 열람)."""
    asset = common.get_or_404(db, Asset, asset_id, "자산")
    return _asset_out(db, asset)


@router.put("/{asset_id}", response_model=schemas.AssetListItem)
def update_asset(
    asset_id: str,
    payload: schemas.AssetUpdate,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """자산 수정 — 전달된 필드만 반영. auth_value 전달 시 재암호화(빈 문자열은 삭제)."""
    asset = common.get_or_404(db, Asset, asset_id, "자산")
    data = payload.model_dump(exclude_unset=True)
    if data.get("client_id"):
        common.get_or_404(db, Client, data["client_id"], "고객사")
    for field in _ASSET_FIELDS:
        if field in data:
            setattr(asset, field, data[field])
    if "auth_value" in data:
        _store_auth_value(asset, asset.auth_type, data["auth_value"])
    db.commit()
    db.refresh(asset)
    return _asset_out(db, asset)


@router.delete("/{asset_id}", response_model=schemas.MessageResponse)
def delete_asset(
    asset_id: str,
    user: User = Depends(require_role("MANAGER")),
    db: Session = Depends(get_db),
):
    """자산 삭제 — MANAGER 이상(§10.1). 사업 매핑에 연결된 자산은 삭제 불가."""
    asset = common.get_or_404(db, Asset, asset_id, "자산")
    referenced = (
        db.query(ProjectClientMap).filter(ProjectClientMap.asset_id == asset_id).count()
    )
    if referenced:
        raise HTTPException(
            status_code=409,
            detail="감축 사업 매핑에 연결된 자산은 삭제할 수 없습니다 — 매핑을 먼저 해제하세요",
        )
    db.delete(asset)
    db.commit()
    return schemas.MessageResponse(message="자산이 삭제되었습니다")


@router.post("/{asset_id}/reveal-auth", response_model=schemas.AssetRevealOut)
def reveal_auth(
    asset_id: str,
    user: User = Depends(require_permission("asset.reveal_auth")),
    db: Session = Depends(get_db),
):
    """인증정보 일시 복호화 (SCR-04 보안 흐름) — 반드시 tb_audit_log에 기록.

    - 평문은 응답으로만 반환(프론트 5초 자동 숨김) — 감사 로그에 값 기록 절대 금지(R2-E6)
    - 키 미설정 시 503
    """
    asset = common.get_or_404(db, Asset, asset_id, "자산")
    encrypted = asset.login_password or asset.api_token
    if not encrypted:
        raise HTTPException(status_code=404, detail="저장된 인증정보가 없습니다")

    plaintext = crypto.decrypt(encrypted)  # 키 미설정 시 여기서 503

    # 감사 로그 — 누가·언제·어떤 자산 (값은 기록 금지)
    AuditLogger.reveal_auth_access(db, user.user_id, asset.asset_id)
    db.commit()
    return schemas.AssetRevealOut(
        asset_id=asset.asset_id,
        auth_type=asset.auth_type,
        login_id=asset.login_id,
        auth_value=plaintext,
        revealed_at=utcnow(),
    )
