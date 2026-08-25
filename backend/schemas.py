"""Pydantic 스키마 — P0(auth·users·health) + P1(고객사·이력·일정·보고서·문서·대시보드)
+ P2(자산·감축 사업·정산) + P3(카카오 채널·채팅 상담) + 세그먼트 발송."""

import json
import re
from datetime import date, datetime
from typing import Dict, List, Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

# 간단 이메일 형식 검증 — email-validator 의존성 없이 정규식만 (P1-C).
# RFC 완전 준수가 목적이 아니라 오타(@ 누락·공백 등) 조기 차단이 목적.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def reject_tz_aware(value: Optional[datetime]) -> Optional[datetime]:
    """벽시계(KST naive) 규약 검증 (#6 P3) — tz-aware 입력(Z·+09:00 등)은 ValueError(→422).

    저장 컬럼이 TIMESTAMP WITHOUT TIME ZONE이라 tzinfo가 조용히 잘려 9시간 어긋난
    시각이 저장되는 사고를 입력 시점에 차단한다. activity_date·일정 start/end 등
    사용자가 벽시계로 입력하는 필드 전용(created_at 계열 서버 시각과 무관)."""
    if value is not None and value.tzinfo is not None:
        raise ValueError("시간대 없는 KST 시각으로 입력하세요")
    return value


def validate_email_format(value: Optional[str]) -> Optional[str]:
    """이메일 형식 검증 — None/빈 문자열은 미입력(None)으로 통과, 형식 오류는 ValueError(→422)."""
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if not _EMAIL_RE.match(stripped):
        raise ValueError("이메일 형식이 올바르지 않습니다: {0}".format(value))
    return stripped


# FK 필드에 빈/공백 문자열이 들어가면 Postgres FK 위반(존재하지 않는 사용자·고객사 등)으로
# 전역 IntegrityError 핸들러가 409를 던진다. 폼에서 미선택 드롭다운이 ''를 보내는 경우가 대표적
# (SQLite 테스트는 FK 미강제라 안 잡힘). 입력 스키마 공통 베이스로 FK 필드명만 골라 '' → None 정규화.
_FK_FIELD_NAMES = frozenset({
    "manager_id", "client_id", "asset_id", "history_id", "sub_id", "assigned_manager_id",
    "project_id", "parent_schedule_id", "related_history_id", "doc_id", "pinned_doc_id",
    "kakao_contact_id",
})


class BlankFKToNoneModel(BaseModel):
    """입력 스키마 공통 베이스 — FK 필드의 빈/공백 문자열을 None으로 정규화(비-FK 필드는 불변)."""

    @model_validator(mode="before")
    @classmethod
    def _blank_fk_to_none(cls, data):
        if not isinstance(data, dict):
            return data
        return {
            k: (None if k in _FK_FIELD_NAMES and isinstance(v, str) and v.strip() == "" else v)
            for k, v in data.items()
        }


# ---------------------------------------------------------------------------
# 공통
# ---------------------------------------------------------------------------
class MessageResponse(BaseModel):
    message: str


class GeocodeBackfillResult(BaseModel):
    """좌표 미등록 고객사 일괄 지오코딩 결과 (SCR-09)."""

    updated: int  # 이번 배치에서 좌표를 채운 건수
    failed: int  # 조회했으나 좌표를 못 찾은 건수
    remaining: int  # 아직 좌표가 없는(다음 배치) 건수


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str
    database_available: bool


# ---------------------------------------------------------------------------
# 사용자
# ---------------------------------------------------------------------------
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    email: str
    name: Optional[str] = None
    position: Optional[str] = None
    auth_provider: Optional[str] = None
    role: str
    status: str
    pin_set: bool = False  # pin_hash 노출 금지 — 설정 여부만
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AccessGroupBrief(BaseModel):
    """내 소속 그룹 요약 — /users/me 용(G1)."""

    group_id: str
    name: str
    home_path: Optional[str] = None
    implicit: bool = False  # 명시 배정 없이 기본(전사) 그룹을 암묵 상속한 경우


class UserMeOut(UserOut):
    """/users/me 확장 — 그룹·허용 메뉴·로그인 홈(G1). 목록 API는 UserOut 유지."""

    groups: List[AccessGroupBrief] = []
    allowed_menus: List[str] = []  # 소속 그룹 허용 메뉴 합집합(ADMIN은 전체)
    home_path: str = "/dashboard"  # 로그인 자동 랜딩(우선순위 최상 그룹의 home)
    access_mode: str = "off"  # off/monitor/enforce — 프론트는 enforce일 때만 메뉴 필터·가드


class UserApproveRequest(BaseModel):
    """가입 승인 (PENDING→ACTIVE) — role 지정 (CR-1)."""

    role: str = Field(default="STAFF", pattern="^(ADMIN|MANAGER|STAFF|OBSERVER)$")


class UserRoleRequest(BaseModel):
    role: str = Field(pattern="^(ADMIN|MANAGER|STAFF|OBSERVER)$")


class UserCreateRequest(BaseModel):
    """관리자 직접 계정 생성 — 즉시 ACTIVE (최초 로그인 시 PIN 설정)."""

    email: str = Field(min_length=3, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    name: Optional[str] = Field(default=None, max_length=50)
    position: Optional[str] = Field(default=None, max_length=50)
    role: str = Field(default="STAFF", pattern="^(ADMIN|MANAGER|STAFF|OBSERVER)$")


class UserUpdateRequest(BaseModel):
    """계정 정보 수정 — 이름·직급만."""

    name: Optional[str] = Field(default=None, max_length=50)
    position: Optional[str] = Field(default=None, max_length=50)


# ---------------------------------------------------------------------------
# 인증
# ---------------------------------------------------------------------------
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class TokenPair(BaseModel):
    """access+refresh 쌍 — 포털 매직링크 verify 응답(user 정보 없이 토큰만, INC-5)."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MagicVerifyIn(BaseModel):
    """매직링크 토큰 검증 요청 — 토큰 자체가 인증(별도 인증 헤더 불요)."""

    token: str = Field(min_length=1)


class PortalMe(BaseModel):
    """로그인한 외부 사용자 신원 — /users/me는 외부역할 403이라 포털 전용으로 제공(INC-7a)."""

    user_id: str
    name: str
    role: str
    org_name: Optional[str] = None


class ExternalAccountIn(BaseModel):
    """외부 포털 계정 provision 요청 (INC-6, 부록 N.8 D3).

    내부 users 관리(role 정규식 ^(ADMIN|MANAGER|STAFF|OBSERVER)$)와 분리된 전용 입력 —
    외부역할(PARTNER/INVESTOR)만 허용한다. client_id/buyer_id 필수 여부는 역할별로
    라우터에서 검증(PARTNER=client_id, INVESTOR=buyer_id).
    """

    email: str = Field(min_length=3, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    name: Optional[str] = Field(default=None, max_length=50)
    role: str = Field(pattern="^(PARTNER|INVESTOR)$")
    # 이용권 기간 — 1d(1일권)/7d(1주권)/30d(1개월권)/365d(연간권). 링크 유효기간=이용권 기간.
    duration: str = Field(default="30d", pattern="^(1d|7d|30d|365d)$")
    client_id: Optional[str] = None  # PARTNER 필수 — 운수사(TRANSPORT)
    buyer_id: Optional[str] = None  # INVESTOR 필수 — 매수자
    kakao_contact_id: Optional[str] = None  # 주어지면 KakaoContact.client_id로 보강(브릿지)
    phone: Optional[str] = Field(default=None, max_length=20)  # 매직링크 알림톡 발송 대상(INC-9)


class ExternalAccountResendIn(BaseModel):
    """재발급 입력 — 이용권 기간 재설정(기본 1개월권)."""

    duration: str = Field(default="30d", pattern="^(1d|7d|30d|365d)$")


class ExternalAccountOut(BaseModel):
    """외부 포털 계정 응답 — magic_link는 발급/재발급 시에만 채우고 목록에선 None."""

    model_config = ConfigDict(from_attributes=True)

    user_id: str
    email: str
    name: Optional[str] = None
    role: str
    client_id: Optional[str] = None
    buyer_id: Optional[str] = None
    status: str
    phone: Optional[str] = None
    portal_expires_at: Optional[datetime] = None  # 이용권 만료(만료 후 로그인 차단)
    magic_link: Optional[str] = None
    # 매직링크 발송 결과(발급/재발급 응답에만, INC-10 정규화): EMAIL_SENT / EMAIL_FAILED /
    # KAKAO_SENT / KAKAO_FAILED / NOT_CONFIGURED. 목록은 None
    delivery: Optional[str] = None


class AuthorizeResponse(BaseModel):
    authorize_url: str
    state: str


class DevLoginRequest(BaseModel):
    email: str = Field(min_length=3, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailLoginRequest(BaseModel):
    """도메인 제한 이메일+PIN 로그인 (네이버웍스 미연동 기간의 기본 수단)."""

    email: str = Field(min_length=3, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    pin: Optional[str] = Field(default=None, max_length=6)


class EmailLoginResponse(BaseModel):
    """status: OK(토큰 포함) / PIN_REQUIRED / PENDING."""

    status: str
    message: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    user: Optional[UserOut] = None


class RefreshRequest(BaseModel):
    refresh_token: str


class PinRequest(BaseModel):
    pin: str = Field(min_length=4, max_length=6)


class PinVerifyResponse(BaseModel):
    verified: bool


# ---------------------------------------------------------------------------
# P1 — 보고서 구독 (tb_report_subscription)
# ---------------------------------------------------------------------------
class ReportSubscriptionIn(BaseModel):
    """고객사 등록/수정 폼의 '월간 보고서 설정' (SCR-03)."""

    report_type: str = Field(min_length=1, max_length=50)
    channel: str = Field(default="EMAIL", pattern="^(EMAIL|KAKAO|BOTH)$")
    due_day: Optional[int] = Field(default=None, ge=1, le=31)
    active: str = Field(default="Y", pattern="^[YN]$")
    # 고객사별 메일 템플릿 오버라이드 — null이면 전역 기본(tb_config → 코드 기본값)
    mail_subject: Optional[str] = Field(default=None, max_length=200)
    mail_body: Optional[str] = None

    @field_validator("active", mode="before")
    @classmethod
    def _coerce_active(cls, v):
        """JSON boolean도 수용 — true→"Y", false→"N" (외부 연동 혼동 방지)."""
        if isinstance(v, bool):
            return "Y" if v else "N"
        return v


class ReportSubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sub_id: str
    client_id: str
    report_type: str
    channel: Optional[str] = None
    due_day: Optional[int] = None
    active: Optional[str] = None
    mail_subject: Optional[str] = None
    mail_body: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# P1 — 고객사 (SCR-03 / 03D)
# ---------------------------------------------------------------------------
class ClientCreate(BaseModel):
    # 구분(client_type)은 공통 코드 마스터(tb_code, category=CLIENT_TYPE)로 관리.
    # 유효성은 라우터에서 활성 코드 존재 여부로 검증(정규식 하드코딩 제거).
    client_type: str = Field(min_length=1, max_length=20)
    company_name: str = Field(min_length=1, max_length=100)
    # max_length는 models.py String(N) 길이와 일치 — 초과 시 DB 오류(500) 대신 422 (#6 P1)
    biz_reg_no: Optional[str] = Field(default=None, max_length=20)
    region: Optional[str] = Field(default=None, max_length=20)
    address: Optional[str] = Field(default=None, max_length=200)
    ceo_name: Optional[str] = Field(default=None, max_length=50)
    ceo_contact_phone: Optional[str] = Field(default=None, max_length=20)
    ceo_contact_email: Optional[str] = Field(default=None, max_length=100)
    main_contact_name: Optional[str] = Field(default=None, max_length=50)
    main_contact_phone: Optional[str] = Field(default=None, max_length=20)
    main_contact_email: Optional[str] = Field(default=None, max_length=100)
    # contract_status는 공통 코드 마스터(CONTRACT_STATUS)로 관리 → 라우터에서 검증
    contract_status: str = Field(default="ACTIVE", min_length=1, max_length=20)
    contract_date: Optional[datetime] = None
    keyman: Optional[str] = Field(default=None, max_length=50)
    manager_id: Optional[str] = Field(default=None, max_length=50)
    report_yn: str = Field(default="N", pattern="^[YN]$")
    lat: Optional[float] = None
    lng: Optional[float] = None
    # 운수사 명부 추가 정보(선택)
    fax: Optional[str] = Field(default=None, max_length=20)
    corp_reg_no: Optional[str] = Field(default=None, max_length=20)  # 법인등록번호
    license_date: Optional[date] = None  # 면허일자
    bus_city: Optional[int] = None
    bus_rural: Optional[int] = None
    bus_intercity: Optional[int] = None
    subscription: Optional[ReportSubscriptionIn] = None  # 월간 보고서 설정

    @model_validator(mode="before")
    @classmethod
    def _blank_to_none(cls, data):
        """빈/공백 문자열을 None으로 정규화 — 특히 FK인 manager_id에 ''가 들어가면 Postgres가
        FK 위반(존재하지 않는 사용자)으로 409를 던진다. 미입력 선택 필드도 '' 대신 null로 저장.
        필수(구분·고객사명·계약상태)는 제외 — 실제 미입력이면 기존 min_length 검증이 잡는다."""
        if not isinstance(data, dict):
            return data
        keep = {"client_type", "company_name", "contract_status"}
        return {
            k: (None if isinstance(v, str) and v.strip() == "" and k not in keep else v)
            for k, v in data.items()
        }

    @field_validator("ceo_contact_email", "main_contact_email")
    @classmethod
    def _check_email(cls, v):
        """이메일 형식 검증 (P1-C) — 오타 주소로 보고서 발송이 실패하는 사고 방지."""
        return validate_email_format(v)

    @field_validator("contract_date")
    @classmethod
    def _check_naive(cls, v):
        """벽시계 KST naive만 허용 (#6 P3)."""
        return reject_tz_aware(v)


class ClientUpdate(BaseModel):
    client_type: Optional[str] = Field(default=None, min_length=1, max_length=20)
    company_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    # max_length는 ClientCreate와 동일 — models.py String(N) 정합 (#6 P1)
    biz_reg_no: Optional[str] = Field(default=None, max_length=20)
    region: Optional[str] = Field(default=None, max_length=20)
    address: Optional[str] = Field(default=None, max_length=200)
    ceo_name: Optional[str] = Field(default=None, max_length=50)
    ceo_contact_phone: Optional[str] = Field(default=None, max_length=20)
    ceo_contact_email: Optional[str] = Field(default=None, max_length=100)
    main_contact_name: Optional[str] = Field(default=None, max_length=50)
    main_contact_phone: Optional[str] = Field(default=None, max_length=20)
    main_contact_email: Optional[str] = Field(default=None, max_length=100)
    contract_status: Optional[str] = Field(default=None, min_length=1, max_length=20)
    contract_date: Optional[datetime] = None
    keyman: Optional[str] = Field(default=None, max_length=50)
    manager_id: Optional[str] = Field(default=None, max_length=50)
    report_yn: Optional[str] = Field(default=None, pattern="^[YN]$")
    lat: Optional[float] = None
    lng: Optional[float] = None
    subscription: Optional[ReportSubscriptionIn] = None

    @model_validator(mode="before")
    @classmethod
    def _blank_to_none(cls, data):
        """빈/공백 문자열을 None으로 정규화 — FK인 manager_id의 '' FK 위반(→409) 방지 및 미입력
        선택 필드를 null로 저장(ClientCreate와 동일). 필수(구분·고객사명·계약상태)는 제외 —
        빈값으로 오면 min_length 검증이 깔끔한 422로 잡도록 ''를 유지한다."""
        if not isinstance(data, dict):
            return data
        keep = {"client_type", "company_name", "contract_status"}
        return {
            k: (None if isinstance(v, str) and v.strip() == "" and k not in keep else v)
            for k, v in data.items()
        }

    @field_validator("ceo_contact_email", "main_contact_email")
    @classmethod
    def _check_email(cls, v):
        """이메일 형식 검증 (P1-C) — ClientCreate와 동일 규칙."""
        return validate_email_format(v)

    @field_validator("contract_date")
    @classmethod
    def _check_naive(cls, v):
        """벽시계 KST naive만 허용 (#6 P3)."""
        return reject_tz_aware(v)


class TransportRosterCreate(ClientCreate):
    """운수사 명부(민원대응 회원명부) 일괄등록 — client_type 기본 TRANSPORT.

    ClientCreate를 상속해 검증·정규화를 그대로 재사용하고, 구분 컬럼이 없는
    운수사 명부용으로 client_type만 기본값(운수사)으로 완화한다.
    """

    client_type: str = Field(default="TRANSPORT", min_length=1, max_length=20)


class ClientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    client_id: str
    client_type: str
    company_name: str
    biz_reg_no: Optional[str] = None
    region: Optional[str] = None
    address: Optional[str] = None
    ceo_name: Optional[str] = None
    ceo_contact_phone: Optional[str] = None
    ceo_contact_email: Optional[str] = None
    main_contact_name: Optional[str] = None
    main_contact_phone: Optional[str] = None
    main_contact_email: Optional[str] = None
    contract_status: Optional[str] = None
    contract_date: Optional[datetime] = None
    keyman: Optional[str] = None
    manager_id: Optional[str] = None
    manager_name: Optional[str] = None
    report_yn: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    fax: Optional[str] = None
    corp_reg_no: Optional[str] = None
    license_date: Optional[date] = None
    bus_city: Optional[int] = None
    bus_rural: Optional[int] = None
    bus_intercity: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @computed_field  # 등록 상태(파생) — 사업자번호 있으면 정식(VERIFIED), 없으면 대기(PENDING)
    @property
    def reg_status(self) -> str:
        return "VERIFIED" if (self.biz_reg_no or "").strip() else "PENDING"
    # 고객사별 참여 집계 — ProjectVehicle(참여 차량, v19.3 정본) group_by 파생(목록·상세 공통)
    participating_vehicle_count: Optional[int] = None
    participating_project_count: Optional[int] = None
    total_reduction: Optional[float] = None
    total_expected_payout: Optional[float] = None


class ClientListItem(ClientOut):
    """목록 행 — 최근 활동 일시 + 이번 달 보고서 상태 미니 배지."""

    last_activity_at: Optional[datetime] = None
    report_status_this_month: Optional[str] = None


class ClientListResponse(BaseModel):
    items: List[ClientListItem]
    total: int


class ClientDetailOut(ClientOut):
    subscriptions: List[ReportSubscriptionOut] = []


# ---------------------------------------------------------------------------
# P1-C — 보고서 수신자 (tb_report_recipient)
# ---------------------------------------------------------------------------
class RecipientCreate(BlankFKToNoneModel):
    """수신자 등록 — sub_id null이면 전 보고서 유형 공통 (R2-B8)."""

    email: str = Field(max_length=100)
    name: Optional[str] = Field(default=None, max_length=50)
    cc_yn: str = Field(default="N", pattern="^[YN]$")
    sub_id: Optional[str] = None  # null=전 유형 공통

    @field_validator("email")
    @classmethod
    def _check_email(cls, v):
        """이메일 형식 검증 (P1-C) — 수신자는 필수값이라 빈 값도 형식 오류로 처리."""
        checked = validate_email_format(v)
        if not checked:
            raise ValueError("이메일 형식이 올바르지 않습니다: {0}".format(v))
        return checked


class RecipientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    recipient_id: str
    client_id: str
    name: Optional[str] = None
    email: str
    cc_yn: Optional[str] = None
    sub_id: Optional[str] = None  # null=전 유형 공통 (R2-B8)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AssetOut(BaseModel):
    """자산 축약형(SCR-03D 탭) — 인증정보(login_password/api_token)는 절대 미노출(reveal은 P2)."""

    model_config = ConfigDict(from_attributes=True)

    asset_id: str
    client_id: str
    asset_group: str
    asset_type: Optional[str] = None
    quantity: Optional[int] = None
    main_spec: Optional[str] = None
    telemetry_yn: Optional[str] = None
    location_info: Optional[str] = None
    status: Optional[str] = None
    agency_name: Optional[str] = None
    site_url: Optional[str] = None
    auth_type: Optional[str] = None
    login_id: Optional[str] = None
    usage_purpose: Optional[str] = None
    has_credentials: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# P2 — 자산 및 연동 (SCR-04)
# ---------------------------------------------------------------------------
class AssetCreate(BlankFKToNoneModel):
    """자산 등록 — auth_value(평문 인증정보)는 서버 AES-256-GCM 암호화 후 저장, 응답 미포함."""

    client_id: str = Field(max_length=50)
    # asset_group·asset_type·status는 공통 코드 마스터(tb_code)로 관리 → 라우터에서 검증
    asset_group: str = Field(min_length=1, max_length=20)
    asset_type: Optional[str] = Field(default=None, max_length=50)  # ICE/EV/SOLAR/HEATPUMP 등
    quantity: Optional[int] = Field(default=None, ge=0)
    # max_length는 models.py String(N) 길이와 일치 — 초과 시 DB 오류(500) 대신 422 (#6 P1)
    main_spec: Optional[str] = Field(default=None, max_length=100)
    telemetry_yn: str = Field(default="N", pattern="^[YN]$")
    location_info: Optional[str] = Field(default=None, max_length=200)
    status: str = Field(default="ACTIVE", min_length=1, max_length=20)
    agency_name: Optional[str] = Field(default=None, max_length=100)
    site_url: Optional[str] = Field(default=None, max_length=255)
    auth_type: str = Field(default="NONE", pattern="^(ID_PW|API_KEY|NONE)$")
    login_id: Optional[str] = Field(default=None, max_length=100)
    # 평문 상한은 라우터에서 암호문 길이로 최종 검증(암호화 팽창 — String(255)/(500))
    auth_value: Optional[str] = None  # ID_PW=비밀번호 / API_KEY=토큰 — 평문 저장 절대 금지
    usage_purpose: Optional[str] = Field(default=None, max_length=100)


class AssetUpdate(BlankFKToNoneModel):
    """자산 수정 — 전달된 필드만 반영. auth_value 전달 시 재암호화(빈 문자열은 삭제)."""

    client_id: Optional[str] = Field(default=None, max_length=50)
    asset_group: Optional[str] = Field(default=None, min_length=1, max_length=20)
    asset_type: Optional[str] = Field(default=None, max_length=50)
    quantity: Optional[int] = Field(default=None, ge=0)
    # max_length는 AssetCreate와 동일 — models.py String(N) 정합 (#6 P1)
    main_spec: Optional[str] = Field(default=None, max_length=100)
    telemetry_yn: Optional[str] = Field(default=None, pattern="^[YN]$")
    location_info: Optional[str] = Field(default=None, max_length=200)
    status: Optional[str] = Field(default=None, min_length=1, max_length=20)
    agency_name: Optional[str] = Field(default=None, max_length=100)
    site_url: Optional[str] = Field(default=None, max_length=255)
    auth_type: Optional[str] = Field(default=None, pattern="^(ID_PW|API_KEY|NONE)$")
    login_id: Optional[str] = Field(default=None, max_length=100)
    auth_value: Optional[str] = None
    usage_purpose: Optional[str] = Field(default=None, max_length=100)


class AccountCheckStatus(BaseModel):
    """계정별 월별 점검 상태 — 점검 이슈(결정적 PK)에서 라이브 도출. 계정 관리 뷰 전용.

    state: NOT_CREATED(이번 달 이슈 미생성) | PENDING(진행 중) | ISSUE(이상·긴급) | DONE(완료).
    담당자가 이슈를 처리(CLOSED)하면 계정 화면 상태도 자동 반영된다(비정규화 없음).
    """

    period: str
    state: str
    issue_status: Optional[str] = None  # OPEN/IN_PROGRESS/HOLD/CLOSED
    priority: Optional[str] = None       # URGENT/NORMAL
    issue_id: Optional[str] = None       # 이슈 보드 딥링크용


class AccountCheckSummary(BaseModel):
    """계정 관리 상단 요약 — 대상 기간 점검 진척(전체/완료/미완료/이상/미생성)."""

    period: str
    total: int
    done: int
    pending: int
    issue: int
    not_created: int


class AssetListItem(AssetOut):
    """자산 목록 행 (SCR-04) — 고객사명 조인. 인증정보는 has_credentials·auth_type만."""

    client_name: Optional[str] = None
    check_status: Optional[AccountCheckStatus] = None  # 계정 관리 뷰(credentials_only)에서만 채움


class AssetListResponse(BaseModel):
    items: List[AssetListItem]
    total: int
    check_summary: Optional[AccountCheckSummary] = None  # 계정 관리 뷰에서만 채움


class AssetRevealOut(BaseModel):
    """reveal-auth 응답 — 일시 복호화 평문(프론트 5초 자동 숨김). 호출은 감사 로그 필수."""

    asset_id: str
    auth_type: Optional[str] = None
    login_id: Optional[str] = None
    auth_value: str
    revealed_at: datetime


# ---------------------------------------------------------------------------
# P2 — 감축 사업 (SCR-06)
# ---------------------------------------------------------------------------
_PROJECT_STATUS_PATTERN = "^(기획|등록완료|모니터링|검증|발급완료)$"


# 발행량 상한 — 컬럼 Numeric(10,2)(정수부 8자리) 초과 시 DB 오류(500) 대신 422 (#6 P2)
_CREDITS_MAX = 99_999_999.99
# 단가 상한 — 상식적 상한(#6 P2). Numeric(15,2) 최대(<1e13)보다 보수적으로 잡는다
_UNIT_PRICE_MAX = 1e12
# 지급 파라미터 상한(부록 L). max_payment=차량당 상한(Numeric(15,2)), base_reduction=기준감축량
# (Numeric(10,3) → <1e7), base_vehicle_age=기준차령(Numeric(5,2) → <1000)
_MAX_PAYMENT_MAX = 1e12
_BASE_REDUCTION_MAX = 9_999_999.999
_BASE_AGE_MAX = 999.99


class ProjectCreate(BlankFKToNoneModel):
    client_id: Optional[str] = Field(default=None, max_length=50)  # 묶음 사업 시 대표사
    project_name: str = Field(min_length=1, max_length=200)
    reg_code: Optional[str] = Field(default=None, max_length=50)  # 예: R-2024-KR-03-000528
    # project_status는 공통 코드 마스터(PROJECT_STATUS)로 관리 → 라우터에서 검증
    project_status: str = Field(default="기획", min_length=1, max_length=20)
    approval_status: Optional[str] = Field(default=None, max_length=20)  # APPROVAL_STATUS(미승인/승인)
    reg_date: Optional[date] = None
    credit_start_date: Optional[date] = None
    credit_end_date: Optional[date] = None
    credit_period_type: Optional[str] = Field(default=None, max_length=20)
    mon_start_date: Optional[date] = None
    mon_end_date: Optional[date] = None
    mon_cycle: Optional[str] = Field(default=None, max_length=50)
    expected_issue_date: Optional[date] = None
    expected_credits: Optional[float] = Field(default=None, ge=0, le=_CREDITS_MAX)
    # 지급 파라미터(max_payment·base_reduction·base_vehicle_age·approved_at)는 여기서 받지 않는다 —
    # PayoutParamsUpdate 전용 엔드포인트만 정본(차량 파생 재계산 동반, 부록 L). 단일 쓰기 경로.
    issued_credits: Optional[float] = Field(default=None, ge=0, le=_CREDITS_MAX)
    issued_at: Optional[date] = None
    manager_id: Optional[str] = Field(default=None, max_length=50)


class ProjectUpdate(BlankFKToNoneModel):
    client_id: Optional[str] = Field(default=None, max_length=50)
    project_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    reg_code: Optional[str] = Field(default=None, max_length=50)
    project_status: Optional[str] = Field(default=None, min_length=1, max_length=20)
    reg_date: Optional[date] = None
    credit_start_date: Optional[date] = None
    credit_end_date: Optional[date] = None
    credit_period_type: Optional[str] = Field(default=None, max_length=20)
    mon_start_date: Optional[date] = None
    mon_end_date: Optional[date] = None
    mon_cycle: Optional[str] = Field(default=None, max_length=50)
    expected_issue_date: Optional[date] = None
    expected_credits: Optional[float] = Field(default=None, ge=0, le=_CREDITS_MAX)
    # 지급 파라미터는 PayoutParamsUpdate 전용 엔드포인트만 정본(차량 재계산 동반) — 단일 쓰기 경로.
    issued_credits: Optional[float] = Field(default=None, ge=0, le=_CREDITS_MAX)
    issued_at: Optional[date] = None
    manager_id: Optional[str] = Field(default=None, max_length=50)
    # 사업 승인상태(APPROVAL_STATUS: 미승인/승인) — 라우터에서 validate_active_code 검증. 미착품 전환 스위치(부록 L)
    approval_status: Optional[str] = Field(default=None, min_length=1, max_length=20)


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: str
    client_id: Optional[str] = None
    project_name: str
    reg_code: Optional[str] = None
    project_status: str
    reg_date: Optional[date] = None
    credit_start_date: Optional[date] = None
    credit_end_date: Optional[date] = None
    credit_period_type: Optional[str] = None
    mon_start_date: Optional[date] = None
    mon_end_date: Optional[date] = None
    mon_cycle: Optional[str] = None
    expected_issue_date: Optional[date] = None  # D-day 계산용 (SCR-06)
    expected_credits: Optional[float] = None  # 🔒 프론트 마스킹
    max_payment: Optional[float] = None  # 🔒 최대지급액(차량당 상한) — expected_payout 파생 기준(부록 L)
    base_reduction: Optional[float] = None  # 기준감축량(기본 240)
    base_vehicle_age: Optional[float] = None  # 기준차령(기본 8)
    approved_at: Optional[date] = None  # 승인일(승인=NOT NULL)
    approval_status: Optional[str] = None  # 사업 승인상태(미승인/승인) — 미착품 전환 스위치(부록 L)
    issued_credits: Optional[float] = None
    issued_at: Optional[date] = None
    manager_id: Optional[str] = None
    manager_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProjectListItem(ProjectOut):
    """목록 행 — 참여 고객사 수 + 지연 단계 수(Phase 1)."""

    delayed_stage_count: int = 0  # 지연 단계 수(목록 표식용)


class ProjectListResponse(BaseModel):
    items: List[ProjectListItem]
    total: int


class PayoutParamsUpdate(BaseModel):
    """지급 파라미터 수기 입력(부록 L) — expected_payout 파생 기준. 전부 optional.

    max_payment 세팅 시 base_reduction/base_vehicle_age 미전달이면 라우터가 240/8로 초기화.
    approved_at 미전달 & 프로젝트 미승인 시 라우터가 오늘로 자동 세팅.
    """

    max_payment: Optional[float] = Field(default=None, ge=0, le=_MAX_PAYMENT_MAX)
    base_reduction: Optional[float] = Field(default=None, gt=0, le=_BASE_REDUCTION_MAX)  # 예상지급액 분모 — 0 금지
    base_vehicle_age: Optional[float] = Field(default=None, gt=0, le=_BASE_AGE_MAX)  # 예상지급액 분모 — 0 금지
    approved_at: Optional[date] = None


class ProjectStageOut(BaseModel):
    """사업 진행 단계 1건 (Phase 1) — delayed는 서버가 판정(예정경과 & 미도달)."""

    model_config = ConfigDict(from_attributes=True)

    stage_code: str
    planned_date: Optional[date] = None
    actual_date: Optional[date] = None
    sort_order: Optional[int] = None
    delayed: bool = False


class ProjectStageIn(BaseModel):
    stage_code: str = Field(max_length=20)
    planned_date: Optional[date] = None
    actual_date: Optional[date] = None


class ProjectStagesUpdate(BaseModel):
    """단계 예정일/실제일 일괄 편집 — 전달된 stage_code만 반영."""

    stages: List[ProjectStageIn]


class ProjectStageAlert(BaseModel):
    """단계 지연/임박 알림 1건 (관찰 대시보드용)."""

    project_id: str
    project_name: str
    stage_code: str
    planned_date: date
    days: int  # 지연=경과일(양수), 임박=남은일(양수). 구분은 목록으로.


class ProjectStageAlertsOut(BaseModel):
    delayed: List[ProjectStageAlert] = []  # 예정 경과 & 미도달
    imminent: List[ProjectStageAlert] = []  # 예정 임박(D-7 이내) & 미도달


class VehicleIntegrityReport(BaseModel):
    """차량 파생값 정합 감사(DBA P1.4) — 저장값 vs 재계산 불일치(stale) 진단.

    읽기전용: 감사 중 계산상 변경은 전부 rollback(저장 안 함).
    samples는 최대 20건, 필드별 before/after(및 실패 사유)를 dict로 담는다.
    """

    checked: int  # 감사한 총 차량 수
    stale: int  # 저장값과 재계산이 어긋난 차량 수
    samples: List[dict] = []  # 불일치 표본(최대 20건): vehicle_id·project_id·필드별 before/after


# 사업 참여 차량 (Phase 2 — 감축량·예상지급액 ingest, 부록 F.2/G) -----------------
_REDUCTION_YEARS = tuple("reduction_y{0}".format(i) for i in range(1, 11))


class ProjectVehicleIn(BlankFKToNoneModel):
    """차량 등록/수정 — 연차 감축량·도입구분·민간투자비율 ingest. total_reduction은 서버 파생."""

    client_id: Optional[str] = Field(default=None, max_length=50)  # 운수사
    asset_id: Optional[str] = Field(default=None, max_length=50)
    vehicle_no: Optional[str] = Field(default=None, max_length=30)
    region: Optional[str] = Field(default=None, max_length=20)
    introduction_type: Optional[str] = Field(default=None, max_length=20)  # VEHICLE_INTRO
    registered_at: Optional[date] = None
    reduction_y1: Optional[float] = Field(default=None, ge=0)
    reduction_y2: Optional[float] = Field(default=None, ge=0)
    reduction_y3: Optional[float] = Field(default=None, ge=0)
    reduction_y4: Optional[float] = Field(default=None, ge=0)
    reduction_y5: Optional[float] = Field(default=None, ge=0)
    reduction_y6: Optional[float] = Field(default=None, ge=0)
    reduction_y7: Optional[float] = Field(default=None, ge=0)
    reduction_y8: Optional[float] = Field(default=None, ge=0)
    reduction_y9: Optional[float] = Field(default=None, ge=0)
    reduction_y10: Optional[float] = Field(default=None, ge=0)
    private_invest_ratio: Optional[float] = Field(default=None, ge=0, le=100)
    memo: Optional[str] = Field(default=None, max_length=255)


class ProjectVehicleOut(ProjectVehicleIn):
    model_config = ConfigDict(from_attributes=True)

    vehicle_id: str
    project_id: str
    client_name: Optional[str] = None  # 운수사명(조인)
    total_reduction: Optional[float] = None  # 서버 파생(연차 단순합)
    expire_at: Optional[date] = None  # 서버 파생(차령만료일, 부록 L)
    remaining_age: Optional[float] = None  # 서버 파생(잔여차령, 부록 L)
    effective_reduction: Optional[float] = None  # 서버 파생(잔여반영감축량, 부록 L)
    expected_payout: Optional[float] = None  # 서버 파생(예상지급액, 부록 L 정본 산식)


class ProjectVehicleListResponse(BaseModel):
    items: List[ProjectVehicleOut]
    total: int
    total_reduction: float = 0  # 목록 합계(연차 합의 총합)
    total_expected_payout: Optional[float] = None  # 예상지급액 입력분 합(있을 때만)


# 참여 운수사 롤업(사업 참여 차량을 운수사별 집계) --------------------------------
class ProjectOperatorRollup(BaseModel):
    client_id: Optional[str] = None  # 운수사(미지정이면 None)
    client_name: Optional[str] = None  # 운수사명(조인, 미지정은 "미지정")
    vehicle_count: int  # 참여 차량 수
    total_reduction: Optional[float] = None  # 잔여반영감축량 합(coalesce 0)
    total_expected_payout: Optional[float] = None  # 예상지급액 합(전건 None이면 None)


class ProjectOperatorListResponse(BaseModel):
    items: List[ProjectOperatorRollup]
    total: int  # 운수사 수


# 자산관리 > 전기버스 — 크로스-프로젝트 차량 뷰(AV-1, 내부 전용 조회) ------------------
class AssetVehicleRow(BaseModel):
    """여러 사업을 가로지르는 차량 단위 행 — Project·Client 조인 조립(from_attributes 불가)."""

    vehicle_id: str
    project_id: str
    project_name: str  # 조인(Project)
    vehicle_no: Optional[str] = None
    region: Optional[str] = None
    client_id: Optional[str] = None
    client_name: Optional[str] = None  # 조인(Client, 미매칭 None)
    registered_at: Optional[date] = None
    expire_at: Optional[date] = None  # 파생: 차령만료일(부록 L)
    approved_at: Optional[date] = None  # 조인(Project 승인일)
    total_reduction: Optional[float] = None  # 파생(연차 단순합)
    remaining_age: Optional[float] = None  # 파생(잔여차령)
    effective_reduction: Optional[float] = None  # 파생(잔여반영감축량)
    expected_payout: Optional[float] = None  # 파생(예상지급액, 부록 L)
    expected_revenue: Optional[float] = None  # 예상수익 = trunc(effective_reduction × 6개월평균시세), None 안전(B2)
    project_status: Optional[str] = None  # 조인(Project 진행상태)
    approval_status: Optional[str] = None  # 조인(Project 승인상태)
    # 사업 회계 집계값(compute_accounting) — 차량 그레인 아님, 그 차량이 속한 사업값을 그대로 표기
    # ("(사업)" 라벨은 프론트). 같은 사업 차량은 동일값.
    project_revenue: Optional[float] = None  # 사업 매출인식(sale_recognized)
    project_cost: Optional[float] = None  # 사업 원가(product=총매입)
    # 연차(1~10) 감축량 — AV-4 상세용으로 미리 포함
    reduction_y1: Optional[float] = None
    reduction_y2: Optional[float] = None
    reduction_y3: Optional[float] = None
    reduction_y4: Optional[float] = None
    reduction_y5: Optional[float] = None
    reduction_y6: Optional[float] = None
    reduction_y7: Optional[float] = None
    reduction_y8: Optional[float] = None
    reduction_y9: Optional[float] = None
    reduction_y10: Optional[float] = None


class AssetVehicleKpi(BaseModel):
    """차량 KPI(필터 결과 전체 기준, 페이지네이션 전) + 재무 KPI(AV-2).

    차량 KPI(수·감축량·지급액)와 재무 KPI(매출·원가·이익)는 그레인이 다르다.
    재무 KPI는 **필터에 걸린 distinct 사업 전체**의 compute_accounting 합(부분집합 과대계상 방지).
    """

    vehicle_count: int  # 차량 수
    total_reduction: Optional[float] = None  # 총감축량 합(전건 null이면 None)
    effective_reduction_sum: Optional[float] = None  # 잔여반영감축량 합
    expected_payout_sum: Optional[float] = None  # 예상지급액 합
    revenue: Optional[float] = None  # Σ 사업 매출인식(sale_recognized) — distinct 사업 기준
    cost: Optional[float] = None  # Σ 사업 원가(product) — distinct 사업 기준
    profit: Optional[float] = None  # Σ 사업 매출이익(gross_profit) — distinct 사업 기준
    # 예상수익 KPI(B2) — 전체 집계 grain(Σeff × 6개월평균시세). 가시행 합과 불일치 정상(예상지급액과 동일 취급)
    expected_revenue: Optional[float] = None


class AssetVehicleListResponse(BaseModel):
    items: List[AssetVehicleRow]
    total: int  # 필터 결과 총 차량 수
    kpi: AssetVehicleKpi
    market_rate_avg6: Optional[float] = None  # 직전 6개월 평균 매출단가 시세(없으면 None, B2)


# 재무 원장(카본크레딧실 재무 전용, FL-1) — 사업(프로젝트) grain 1행 + 전사 총계 ------
class FinanceLedgerRow(BaseModel):
    """전 감축사업을 사업 grain 1행으로 나열 — Project 마스터 + 회계 원장층 12값(부록 L.3).

    회계값은 compute_accounting 풀 dict를 그대로 표기한다(신규 산식 없음). 조회 전용.
    """

    project_id: str
    project_name: str
    reg_code: Optional[str] = None  # 사업번호(예: R-2020-KR-03-000528)
    approval_status: Optional[str] = None  # 승인상태(미승인/승인)
    approved_at: Optional[date] = None  # 승인일
    # 회계 원장층 12값(compute_accounting)
    product: Optional[float] = None  # 제품(총매입)
    expected_payment: Optional[float] = None  # 예상지급액
    wip1: Optional[float] = None  # 미착품1
    wip2: Optional[float] = None  # 미착품2
    liability: Optional[float] = None  # 지급채무
    inventory: Optional[float] = None  # 재고자산
    payout_rate: Optional[float] = None  # 지급률
    sale_recognized: Optional[float] = None  # 매출인식
    gross_profit: Optional[float] = None  # 매출이익
    profit_rate: Optional[float] = None  # 매출이익률
    ownership_total: Optional[float] = None  # Σ 소유권비율(%)
    # 후시/계약 소유권 분할(FL-2, 조회 전용) — held+sold == ownership_total(None 아닐 때)
    held_qty: Optional[float] = None  # 후시보유 수량 합(tCO2)
    sold_qty: Optional[float] = None  # 판매 계약 수량 합(tCO2)
    held_ownership: Optional[float] = None  # 후시보유 Σ 소유권비율(%)
    sold_ownership: Optional[float] = None  # 판매 계약 Σ 소유권비율(%)
    inventory_valuation: Optional[float] = None  # 재고평가(held_qty × 오늘 시세), None 안전
    expected_revenue: Optional[float] = None  # 예상수익 = trunc(Σeff × 6개월평균시세), None 안전(B2)


class FinanceLedgerTotals(BaseModel):
    """전사 총계 — 필터 전체(페이지 전) 사업 grain 단순 None-안전 합(이중계상 구조적 불가).

    비율(payout_rate·profit_rate)은 합산 무의미이므로 총계에서 제외하고, 총이익률만
    총계 gross_profit/sale_recognized로 파생한다.
    """

    product: Optional[float] = None
    expected_payment: Optional[float] = None
    wip1: Optional[float] = None
    wip2: Optional[float] = None
    liability: Optional[float] = None
    inventory: Optional[float] = None
    sale_recognized: Optional[float] = None
    gross_profit: Optional[float] = None
    profit_rate: Optional[float] = None  # 파생: 총 gross_profit / 총 sale_recognized
    held_qty: Optional[float] = None  # 후시보유 수량 합(FL-2, Σ 행)
    inventory_valuation: Optional[float] = None  # 재고평가 합(FL-2, None 안전)
    expected_revenue: Optional[float] = None  # 예상수익 총계(Σ 사업행, None 안전, B2)


class FinanceLedgerResponse(BaseModel):
    items: List[FinanceLedgerRow]  # page 슬라이스
    total: int  # 필터 결과 총 사업 수
    totals: FinanceLedgerTotals  # 필터 전체 총계
    current_market_rate: Optional[float] = None  # 오늘 현재시세(FL-2, 재고평가 기준단가)
    market_rate_avg6: Optional[float] = None  # 직전 6개월 평균 매출단가 시세(없으면 None, B2)


# 정산 요약 매트릭스(P2 '자산관리 보고') — 운수사×사업 grain 집계 --------------------
class SettlementProjectBreakdown(BaseModel):
    """운수사가 참여한 사업 1건의 정산 요약(드릴다운) — 저장 파생값 합(재계산 없음)."""

    project_id: str
    project_name: str
    vehicle_count: int
    total_reduction: Optional[float] = None  # Σ총감축량(None 안전)
    effective_reduction: Optional[float] = None  # Σ잔여반영감축량(None 안전)
    expected_payout: Optional[float] = None  # Σ예상지급액(None 안전)
    expected_revenue: Optional[float] = None  # 예상수익 = trunc(Σeff × 6개월평균시세), None 안전(B2)


class SettlementSummaryRow(BaseModel):
    """운수사 1행 — 참여 사업 롤업 요약 + 사업별 드릴다운(projects).

    지급 정본은 ProjectVehicle.client_id(차량 소유 운수사). client_id=None은
    '(미지정)' 운수사 행(NULL client_id 차량 집계 — Σ행==총계 정합 보장).
    """

    client_id: Optional[str] = None
    company_name: str
    region: Optional[str] = None
    client_type: Optional[str] = None
    contract_status: Optional[str] = None
    participating_project_count: int  # 그 운수사 distinct 참여 사업수
    participating_vehicle_count: int  # 참여 차량 단순합
    total_reduction: Optional[float] = None
    effective_reduction: Optional[float] = None
    expected_payout: Optional[float] = None
    expected_revenue: Optional[float] = None  # 예상수익 롤업(Σ 셀, None 안전, B2)
    projects: List[SettlementProjectBreakdown]


class SettlementSummaryTotals(BaseModel):
    """전사 총계 — distinct project(중복계상 회피)·차량 단순합·None 안전 감축/지급 합."""

    distinct_project_count: int  # 전체 distinct 사업수(운수사 합산 아님)
    participating_vehicle_count: int
    total_reduction: Optional[float] = None
    effective_reduction: Optional[float] = None
    expected_payout: Optional[float] = None
    expected_revenue: Optional[float] = None  # 예상수익 총계(Σ 셀, None 안전, B2)


class SettlementSummaryResponse(BaseModel):
    items: List[SettlementSummaryRow]  # 운수사 행((미지정) 포함)
    total: int  # 운수사 행 수
    totals: SettlementSummaryTotals  # 전사 총계
    market_rate_avg6: Optional[float] = None  # 직전 6개월 평균 매출단가 시세(없으면 None, B2)


# 운수사 정산내역 능동 통지(P3) — 이메일 정산 명세 발송 미리보기/발송 ------------------
class SettlementNoticePreviewItem(BaseModel):
    """통지 대상 운수사 1건 미리보기 — 발송 전 대상·수신 가능 여부 확인용.

    (미지정) 운수사(client_id=None)는 대상에서 제외되어 여기 나타나지 않는다.
    expected_payout=None(미산정)은 목록엔 포함되나 sendable(실효 발송 대상)에서는 빠진다.
    """

    client_id: str
    company_name: str
    expected_payout: Optional[float] = None  # None이면 '산정 중'(본문 표기)
    participating_vehicle_count: int
    participating_project_count: int
    can_receive: bool  # 공통 수신자 or 주 담당자 이메일 보유
    to_count: int  # TO 수신자 수(0이면 발송 실패 격리 대상)
    # 알림톡 채널(P3 증분) — 수신번호 원천(KakaoContact APPROVED phone or 주 담당자 전화) 보유 여부.
    # 알림톡 미설정(SOLAPI/템플릿)이면 게이트로 전부 false·count 0.
    can_receive_alimtalk: bool = False
    alimtalk_to_count: int = 0  # 알림톡 수신번호 수(0/1)


class SettlementNoticePreviewResponse(BaseModel):
    items: List[SettlementNoticePreviewItem]
    total: int  # 대상 운수사 수((미지정) 제외)
    sendable_count: int  # expected_payout not None & can_receive 인 실효 발송 대상 수
    sendable_alimtalk_count: int = 0  # 금액 산정 완료 & 알림톡 수신번호 & 알림톡 설정 인 대상 수


class SettlementNoticePreviewRequest(BaseModel):
    """정산 명세 미리보기 요청 — 화면 필터 스코프(P2 settlement-summary와 동일 시그니처).

    미지정 시 전사 대상. 이 스코프가 그대로 sendable 판정·화면 목록이 되고, 프론트는 그
    sendable client_id들을 send.client_ids로 전달해 미리보기==발송 대상을 고정한다(표류 차단).

    notice_type: EXPECTED(기본)=live 예정액 고지 / CONFIRMED=확정 header(confirmed_amount) 고지.
    CONFIRMED은 확정 header 있는 운수사만 대상(미확정 제외).
    """

    client_id: Optional[str] = None  # 운수사 필터(ProjectVehicle.client_id)
    client_type: Optional[str] = None  # 고객사 구분 필터(Client.client_type)
    region: Optional[str] = None  # 지역 필터(Client.region)
    notice_type: Literal["EXPECTED", "CONFIRMED"] = "EXPECTED"  # 기본 EXPECTED(무회귀)


class SettlementNoticeSendRequest(BaseModel):
    """정산 명세 발송 요청 — client_ids 미지정 시 sendable 전체 발송.

    subject/body 미지정 시 tb_config(settlement_notice_subject/_body) 오버라이드,
    미저장 시 코드 기본값(services.settlement_notice) 사용.

    notice_type: EXPECTED(기본)=live 예정액 고지 / CONFIRMED=확정 header(confirmed_amount) 고지.
    """

    client_ids: Optional[List[str]] = None  # 특정 운수사 한정(없으면 sendable 전체)
    subject: Optional[str] = None
    body: Optional[str] = None
    notice_type: Literal["EXPECTED", "CONFIRMED"] = "EXPECTED"  # 기본 EXPECTED(무회귀)
    # 발송 채널(P3 증분) — 기본 EMAIL(무회귀). BOTH/ALIMTALK 시 알림톡 병행·단독.
    # 채널별 독립 실패격리. 요청 채널이 전부 미설정이면 503(발송·감사 0).
    channel: Literal["EMAIL", "ALIMTALK", "BOTH"] = "EMAIL"


class SettlementNoticeSendDetail(BaseModel):
    client_id: str
    company_name: str
    result: str  # "SENT" | "FAILED"(기존 계약 유지 — EMAIL 포함 시 이메일 결과, ALIMTALK 단독이면 알림톡 결과)
    reason: Optional[str] = None  # FAILED 사유(수신자 없음 등)
    # 채널별 결과(P3 증분) — 요청 채널만 값 존재. "SENT"|"FAILED"|"SKIPPED"|None(미요청).
    email_result: Optional[str] = None
    alimtalk_result: Optional[str] = None


class SettlementNoticeSendResult(BaseModel):
    target_count: int
    sent: int  # 이메일 발송 성공 수(기존 계약 유지)
    failed: int  # 이메일 발송 실패 수(기존 계약 유지)
    details: List[SettlementNoticeSendDetail]
    alimtalk_sent: int = 0  # 알림톡 발송 성공 수(P3 증분)
    alimtalk_failed: int = 0  # 알림톡 발송 실패 수(P3 증분)


# P4 정산 재건 — 정산 헤더(tb_settlement) 그레인=(고객사×사업). 상태전이 머신 --------------
class SettlementOut(BaseModel):
    """정산 헤더 1건 — 확정 시 동결된 지표·상태·감사 시각 포함. status는 SETTLEMENT_STATUS 코드값."""

    model_config = ConfigDict(from_attributes=True)

    settlement_id: str
    client_id: str
    project_id: str
    period: Optional[str] = None  # 'YYYY-MM' — 단일 정산이면 None
    status: str  # CONFIRMED/BILLED/COMPLETED (SETTLEMENT_STATUS)
    confirmed_amount: Optional[float] = None
    vehicle_count: Optional[int] = None  # 확정 시점 동결
    effective_reduction: Optional[float] = None  # 확정 시점 동결
    confirmed_at: Optional[datetime] = None
    confirmed_by: Optional[str] = None
    billed_at: Optional[datetime] = None
    billed_by: Optional[str] = None
    completed_at: Optional[datetime] = None
    completed_by: Optional[str] = None
    paid_amount: Optional[float] = None  # 완료 시 실입금액
    payment_type: Optional[str] = None  # 지급 구분 코드값
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SettlementListResponse(BaseModel):
    items: List[SettlementOut]
    total: int


class SettlementSnapshotOut(BaseModel):
    """정산 스냅샷 1회차(append-only 감사) — map_id에 settlement_id 보관(재활용)."""

    model_config = ConfigDict(from_attributes=True)

    snapshot_id: str
    map_id: str  # settlement_id(재활용 감사키)
    seq: int
    issued_credits: Optional[float] = None
    amount: Optional[float] = None
    unit_price: Optional[float] = None
    allocation_ratio: Optional[float] = None
    success_fee_rate: Optional[float] = None
    paid_amount: Optional[float] = None
    vehicle_count: Optional[int] = None  # 확정 동결 지표(P4 additive)
    effective_reduction: Optional[float] = None  # 확정 동결 지표(P4 additive)
    action: str  # CONFIRMED/BILLED/REBILLED/REVERTED/COMPLETED
    reason: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None


class SettlementStatusUpdate(BaseModel):
    """정산 상태전이 요청 — target_status는 SETTLEMENT_STATUS 코드값(라우터 검증)."""

    target_status: str  # CONFIRMED/BILLED/COMPLETED
    reason: Optional[str] = Field(default=None, max_length=200)


class SettlementConfirmRequest(BaseModel):
    """정산 확정(freeze) 요청 — (고객사×사업[×기간]) 예정 정산을 CONFIRMED로 동결."""

    client_id: str
    project_id: str
    period: Optional[str] = Field(default=None, max_length=7)  # 'YYYY-MM' — 단일 정산이면 None


class SettlementSnapshotListResponse(BaseModel):
    items: List[SettlementSnapshotOut]
    total: int


# 부서 워크플로우 파이프라인(P4 증분4) — (운수사×사업) 5단계 진행 파생(조회 전용) --------
class PipelineRow(BaseModel):
    """(운수사×사업) 파이프라인 1행 — 수집→결산→정산→보고→통지 5단계 파생 현황.

    stage는 현재 최고 도달 단계 코드(none/collect/accounting/settlement/report/notice),
    next_action은 아직 도달하지 못한 다음 단계의 할일 문자열이다. reported/notified는
    신호 강약이 다르다(services.pipeline 주석): reported는 전역(약한) 신호, notified는
    운수사 활동(정확) 또는 배치 감사(약한 전역). client_id=None은 '(미지정)' 셀(통지 불가).
    """

    client_id: Optional[str] = None
    company_name: str
    project_id: str
    project_name: str
    vehicle_count: int
    has_accounting: bool  # 그 셀에 expected_payout non-null 차량 존재(결산 완료 신호)
    settlement_status: Optional[str] = None  # None=예정 / CONFIRMED·BILLED·COMPLETED(헤더 status)
    reported: bool  # DATA_EXPORT/ASSET_REPORT 감사 존재(전역 약한 신호)
    notified: bool  # 운수사 [자동]정산 EMAIL 이력 or SETTLEMENT_NOTICE_SEND 감사
    stage: str  # 현재 최고 도달 단계 코드
    next_action: str  # 다음 할일(도달 못한 다음 단계 안내)


class PipelineResponse(BaseModel):
    items: List[PipelineRow]
    total: int
    stage_counts: Optional[Dict[str, int]] = None  # 단계 코드별 행 수(요약 카운트)


# 거래계약(매수자별 선물 판매단가) — 프로젝트당 매수자 여럿, 차액 수익 파생 ------------
# 매수자 마스터(증권/투자/금융사) — 투자·금융사 신원의 근본(부록 N.8 D1) --------------
class BuyerIn(BaseModel):
    """매수자 등록 — buyer_type은 SALE_BUYER_TYPE 공통코드(라우터 검증)."""

    name: str = Field(min_length=1, max_length=100)  # 매수자명(증권/투자/금융사)
    buyer_type: Optional[str] = Field(default=None, max_length=20)  # SALE_BUYER_TYPE
    biz_reg_no: Optional[str] = Field(default=None, max_length=20)
    contact_name: Optional[str] = Field(default=None, max_length=50)
    contact_phone: Optional[str] = Field(default=None, max_length=20)
    contact_email: Optional[str] = Field(default=None, max_length=100)
    memo: Optional[str] = Field(default=None, max_length=255)


class BuyerUpdate(BaseModel):
    """매수자 부분 수정 — 전달된 필드만 반영(전 필드 optional)."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    buyer_type: Optional[str] = Field(default=None, max_length=20)
    biz_reg_no: Optional[str] = Field(default=None, max_length=20)
    contact_name: Optional[str] = Field(default=None, max_length=50)
    contact_phone: Optional[str] = Field(default=None, max_length=20)
    contact_email: Optional[str] = Field(default=None, max_length=100)
    memo: Optional[str] = Field(default=None, max_length=255)


class BuyerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    buyer_id: str
    name: str
    buyer_type: Optional[str] = None
    biz_reg_no: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    memo: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # 참여 사업 수(거래계약 보유 distinct 사업) — 목록 조인 보강 필드
    project_count: int = 0


class BuyerListResponse(BaseModel):
    items: List[BuyerOut]
    total: int


class ProjectSaleIn(BaseModel):
    """거래계약 등록/수정 — buyer_type은 SALE_BUYER_TYPE 공통코드(라우터 검증)."""

    buyer_name: str = Field(min_length=1, max_length=100)  # 매수자(증권/투자/금융, 전환기 유지)
    buyer_id: Optional[str] = Field(default=None, max_length=50)  # 매수자 마스터 링크(부록 N.8 D1)
    buyer_type: Optional[str] = Field(default=None, max_length=20)  # SALE_BUYER_TYPE
    sale_unit_price: Optional[float] = Field(default=None, ge=0, le=_UNIT_PRICE_MAX)  # 선물 판매 단가(정보성)
    quantity: Optional[float] = Field(default=None, ge=0, le=_CREDITS_MAX)  # 판매 수량(tCO2, 정보성)
    # 회계 원장층(부록 L.3) — 매출인식 확장 필드
    ownership_pct: Optional[float] = Field(default=None, ge=0, le=100)  # 소유권비율(%)
    sale_invoice_amount: Optional[float] = Field(default=None, ge=0, le=_UNIT_PRICE_MAX)  # 매출세금계산서 실발행액
    sale_invoice_date: Optional[date] = None  # 매출세금계산서 발행일
    sale_payment_date: Optional[date] = None  # 매출세금계산서 입금일(정보성)
    sale_approval_no: Optional[str] = None  # 국세청 승인번호(HTML 자동반영 멱등키)
    is_hold: str = Field(default="N", pattern="^[YN]$")  # 후시보유 여부
    contract_date: Optional[date] = None
    memo: Optional[str] = Field(default=None, max_length=255)


class ProjectSaleUpdate(BaseModel):
    """거래계약 부분 수정 — 전달된 필드만 반영(buyer_name 포함 전 필드 optional)."""

    buyer_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    buyer_id: Optional[str] = Field(default=None, max_length=50)  # 매수자 마스터 링크
    buyer_type: Optional[str] = Field(default=None, max_length=20)
    sale_unit_price: Optional[float] = Field(default=None, ge=0, le=_UNIT_PRICE_MAX)
    quantity: Optional[float] = Field(default=None, ge=0, le=_CREDITS_MAX)
    ownership_pct: Optional[float] = Field(default=None, ge=0, le=100)
    sale_invoice_amount: Optional[float] = Field(default=None, ge=0, le=_UNIT_PRICE_MAX)
    sale_invoice_date: Optional[date] = None
    sale_payment_date: Optional[date] = None  # 매출세금계산서 입금일(정보성)
    sale_approval_no: Optional[str] = None  # 국세청 승인번호(HTML 자동반영 멱등키)
    is_hold: Optional[str] = Field(default=None, pattern="^[YN]$")
    contract_date: Optional[date] = None
    memo: Optional[str] = Field(default=None, max_length=255)


class ProjectSaleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sale_id: str
    project_id: str
    buyer_name: str
    buyer_id: Optional[str] = None  # 매수자 마스터 링크(부록 N.8 D1)
    buyer_type: Optional[str] = None
    sale_unit_price: Optional[float] = None  # 🔒
    quantity: Optional[float] = None
    ownership_pct: Optional[float] = None  # 소유권비율(%)
    sale_invoice_amount: Optional[float] = None  # 🔒 매출세금계산서 실발행액(매출인식 기준)
    sale_invoice_date: Optional[date] = None
    sale_payment_date: Optional[date] = None  # 매출세금계산서 입금일(정보성)
    sale_approval_no: Optional[str] = None  # 국세청 승인번호(HTML 자동반영 멱등키)
    is_hold: Optional[str] = None  # 후시보유 여부
    contract_date: Optional[date] = None
    memo: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProjectSaleListResponse(BaseModel):
    items: List[ProjectSaleOut]
    total: int
    total_sale_amount: Optional[float] = None  # Σ(단가×수량, 둘 다 입력된 계약만) — 없으면 None


# 매출단가 시세 마스터(effective-dated) — 톤당 단가의 시점별 이력 -----------------
class MarketRateIn(BaseModel):
    effective_date: date
    unit_price: float = Field(ge=0)
    note: Optional[str] = Field(default=None, max_length=255)


class MarketRateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rate_id: str
    effective_date: date
    unit_price: float
    note: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None


class EmissionFactorIn(BaseModel):
    fuel_type: str = Field(min_length=1, max_length=20)
    ef_value: float = Field(ge=0)
    unit: Optional[str] = Field(default=None, max_length=20)
    effective_date: date
    note: Optional[str] = Field(default=None, max_length=255)


class ChargingInfraImportResult(BaseModel):
    facilities: int
    chargers: int
    meters: int
    client_matched: int


class ChargingFacilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    facility_id: str
    operator_name: Optional[str] = None
    client_id: Optional[str] = None
    client_name: Optional[str] = None
    region: Optional[str] = None
    address: Optional[str] = None
    charger_count: int = 0
    meter_count: int = 0


class ChargingFacilityListResponse(BaseModel):
    items: List[ChargingFacilityOut]
    total: int


class ChargingInfraSummary(BaseModel):
    facilities: int
    chargers: int
    meters: int
    by_region: List[dict] = []


class EvFinanceImportResult(BaseModel):
    created: int
    client_matched: int


class EvFinanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ev_finance_id: str
    vehicle_no: Optional[str] = None
    vin: Optional[str] = None
    operator_name: Optional[str] = None
    client_id: Optional[str] = None
    client_name: Optional[str] = None
    region: Optional[str] = None
    sido: Optional[str] = None
    model_year: Optional[int] = None
    registered_at: Optional[date] = None
    release_price: Optional[float] = None
    acquisition_tax: Optional[float] = None
    rural_tax: Optional[float] = None
    vehicle_value: Optional[float] = None
    low_floor_subsidy: Optional[float] = None
    ev_subsidy: Optional[float] = None
    self_payment: Optional[float] = None
    private_ratio: Optional[float] = None
    public_ratio: Optional[float] = None
    subsidy_check: Optional[float] = None
    note: Optional[str] = None


class EvFinanceListResponse(BaseModel):
    items: List[EvFinanceOut]
    total: int


class EvFinanceSummary(BaseModel):
    count: int
    vehicle_value_total: float
    subsidy_total: float
    self_payment_total: float
    avg_private_ratio: float


class ReductionRegistryImportResult(BaseModel):
    created: int
    client_matched: int
    baseline: int
    project: int
    candidate: int


class ReductionRegistryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    registry_id: str
    role: str
    vehicle_no: Optional[str] = None
    operator_name: Optional[str] = None
    client_id: Optional[str] = None
    client_name: Optional[str] = None
    introduction_type: Optional[str] = None
    model_name: Optional[str] = None
    vin: Optional[str] = None
    model_year: Optional[int] = None
    vehicle_class: Optional[str] = None
    purpose: Optional[str] = None
    seating_capacity: Optional[int] = None
    fuel: Optional[str] = None
    registered_at: Optional[date] = None
    battery_type: Optional[str] = None
    program_name: Optional[str] = None
    region: Optional[str] = None


class ReductionRegistryListResponse(BaseModel):
    items: List[ReductionRegistryOut]
    total: int


class ReductionRegistrySummary(BaseModel):
    total: int
    baseline: int
    project: int
    candidate: int
    client_matched: int
    by_region: List[dict] = []


class EmissionFactorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    factor_id: str
    fuel_type: str
    ef_value: float
    unit: Optional[str] = None
    effective_date: date
    note: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None


# 변동 이력 스냅샷(append-only, Phase 4 INC-3 / 부록 N.8 D5) — Out만(타임라인 조회는 INC-6)
class ParticipationSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    snapshot_id: str
    project_id: str
    client_id: Optional[str] = None  # 운수사(미지정 허용)
    captured_at: Optional[datetime] = None
    effective_reduction_sum: Optional[float] = None  # Σ 잔여반영감축량
    expected_payout_sum: Optional[float] = None  # Σ 예상지급액
    trigger: Optional[str] = None  # 변동 유발
    created_at: Optional[datetime] = None


class SaleSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    snapshot_id: str
    project_id: str
    sale_id: Optional[str] = None
    buyer_id: Optional[str] = None
    captured_at: Optional[datetime] = None
    quantity: Optional[float] = None  # 판매 수량(tCO2)
    gross_revenue: Optional[float] = None  # 총매출(실발행액 우선)
    trigger: Optional[str] = None
    created_at: Optional[datetime] = None


# 매입세금계산서(운수사 실지급=제품) — 회계 원장층(부록 L.3) 제품 원천 ------------
class PurchaseInvoiceIn(BlankFKToNoneModel):
    """매입세금계산서 등록 — 금액 필수(ge=0). operator_name은 엑셀 import용 운수사 표기."""

    client_id: Optional[str] = Field(default=None, max_length=50)  # 운수사
    operator_name: Optional[str] = Field(default=None, max_length=100)  # 운수사 표기(엑셀 import용)
    region: Optional[str] = Field(default=None, max_length=20)
    issue_date: Optional[date] = None  # 발행일
    payment_date: Optional[date] = None  # 입금일(정보성)
    amount: float = Field(ge=0, le=_UNIT_PRICE_MAX)  # 금액(필수)
    approval_no: Optional[str] = None  # 국세청 승인번호(HTML 자동반영 멱등키)
    memo: Optional[str] = Field(default=None, max_length=255)


class PurchaseInvoiceUpdate(BlankFKToNoneModel):
    """매입세금계산서 부분 수정 — 전달된 필드만 반영(전 필드 optional)."""

    client_id: Optional[str] = Field(default=None, max_length=50)
    operator_name: Optional[str] = Field(default=None, max_length=100)
    region: Optional[str] = Field(default=None, max_length=20)
    issue_date: Optional[date] = None
    payment_date: Optional[date] = None  # 입금일(정보성)
    amount: Optional[float] = Field(default=None, ge=0, le=_UNIT_PRICE_MAX)
    approval_no: Optional[str] = None  # 국세청 승인번호(HTML 자동반영 멱등키)
    memo: Optional[str] = Field(default=None, max_length=255)


class PurchaseInvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    invoice_id: str
    project_id: str
    client_id: Optional[str] = None
    client_name: Optional[str] = None  # 운수사명(조인)
    operator_name: Optional[str] = None
    region: Optional[str] = None
    issue_date: Optional[date] = None
    payment_date: Optional[date] = None  # 입금일(정보성)
    amount: Optional[float] = None  # 🔒
    approval_no: Optional[str] = None  # 국세청 승인번호(HTML 자동반영 멱등키)
    memo: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PurchaseInvoiceListResponse(BaseModel):
    items: List[PurchaseInvoiceOut]
    total: int
    total_amount: Optional[float] = None  # Σ amount(제품=총매입) — 없으면 None


# 세금계산서 원장(홈택스 HTML 자동반영) — 후시 전체 매입/매출 -----------------------------
class TaxInvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tax_invoice_id: str
    approval_no: Optional[str] = None
    direction: Optional[str] = None  # 매입/매출/미상
    invoicer_reg_no: Optional[str] = None
    invoicee_reg_no: Optional[str] = None
    invoicer_name: Optional[str] = None
    invoicee_name: Optional[str] = None
    counterpart_reg_no: Optional[str] = None
    counterpart_name: Optional[str] = None
    issue_date: Optional[date] = None
    supply_amount: Optional[float] = None
    tax_amount: Optional[float] = None
    total_amount: Optional[float] = None
    type_code: Optional[str] = None
    purpose_code: Optional[str] = None
    matched_client_id: Optional[str] = None
    matched_buyer_id: Optional[str] = None
    project_id: Optional[str] = None
    source: Optional[str] = None
    memo: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TaxInvoiceListResponse(BaseModel):
    items: List[TaxInvoiceOut]
    total: int


class TaxInvoiceIssueCounts(BaseModel):
    """정합성 워크리스트 카운트 — 미연결·미매칭·음수(수정취소)."""

    unlinked: int   # 사업(project) 미연결
    unmatched: int  # 상대(운수사/투자사) 마스터 미매칭
    negative: int   # 음수 공급가액(수정취소 등)


class TaxInvoiceBreakdownRow(BaseModel):
    """축별 집계 1행 — 거래처/사업/자사법인별 매입·매출·순액·건수."""

    key: str
    label: str
    purchase: float
    sales: float
    net: float
    count: int


class TaxInvoiceBreakdown(BaseModel):
    axis: str  # counterpart | project | entity
    rows: List[TaxInvoiceBreakdownRow] = []


class TaxInvoiceMonthPoint(BaseModel):
    """월별 매입·매출·순액(공급가액 기준) — 요약 추이 차트용."""

    month: str          # YYYY-MM
    purchase: float     # 매입 공급가액
    sales: float        # 매출 공급가액
    net: float          # 순액(매출 - 매입)


class TaxInvoiceSummary(BaseModel):
    """세금계산서 요약(경영전략실) — 기간 내 매입·매출·순액·부가세 집계 + 월별 추이."""

    purchase_supply: float
    sales_supply: float
    net_supply: float      # 매출 - 매입(공급가액)
    purchase_tax: float
    sales_tax: float
    purchase_count: int
    sales_count: int
    months: List[TaxInvoiceMonthPoint] = []


class TaxInvoicePreviewItem(BaseModel):
    filename: Optional[str] = None
    ok: bool
    reason: Optional[str] = None  # 실패 사유(password_unresolved 등)
    approval_no: Optional[str] = None
    direction: Optional[str] = None
    issue_date: Optional[str] = None  # 'YYYY-MM-DD'
    invoicer_reg_no: Optional[str] = None
    invoicee_reg_no: Optional[str] = None
    invoicer_name: Optional[str] = None
    invoicee_name: Optional[str] = None
    counterpart_reg_no: Optional[str] = None
    counterpart_name: Optional[str] = None
    supply_amount: Optional[int] = None
    tax_amount: Optional[int] = None
    total_amount: Optional[int] = None
    type_code: Optional[str] = None
    purpose_code: Optional[str] = None
    matched_client_id: Optional[str] = None
    matched_client_name: Optional[str] = None
    matched_buyer_id: Optional[str] = None
    matched_buyer_name: Optional[str] = None
    is_duplicate: Optional[bool] = None


class TaxInvoicePreviewResponse(BaseModel):
    items: List[TaxInvoicePreviewItem]


class TaxInvoiceCommitDetail(BaseModel):
    filename: Optional[str] = None
    result: str  # created / duplicate / held
    reason: Optional[str] = None
    approval_no: Optional[str] = None
    tax_invoice_id: Optional[str] = None


class TaxInvoiceCommitResponse(BaseModel):
    total: int
    created: int
    duplicate: int
    held: int
    details: List[TaxInvoiceCommitDetail]


# 운수사 보유 차량(fleet) 마스터 — 부록 M. BUS_Info_list.xlsx 컬럼 반영 --------------
class ClientVehicleIn(BlankFKToNoneModel):
    """차량 마스터 등록 — vehicle_no 필수(전국 유일). operator_name은 업체명 원문(운수사 매칭)."""

    vehicle_no: str = Field(min_length=1, max_length=30)  # 차량번호(필수)
    client_id: Optional[str] = Field(default=None, max_length=50)  # 운수사(업체명 매칭)
    operator_name: Optional[str] = Field(default=None, max_length=100)  # 업체명 원문
    chassis_no: Optional[str] = Field(default=None, max_length=50)  # 차대번호
    model_name: Optional[str] = Field(default=None, max_length=50)  # 차명
    model_year: Optional[int] = Field(default=None, ge=0)  # 연식
    registered_at: Optional[date] = None  # 차량등록일
    vehicle_class: Optional[str] = Field(default=None, max_length=50)  # 차종
    length_mm: Optional[int] = Field(default=None, ge=0)  # 길이(mm)
    width_mm: Optional[int] = Field(default=None, ge=0)  # 너비(mm)
    height_mm: Optional[int] = Field(default=None, ge=0)  # 높이(mm)
    gross_weight_kg: Optional[int] = Field(default=None, ge=0)  # 총중량(kg)
    seating_capacity: Optional[int] = Field(default=None, ge=0)  # 승차정원
    fuel: Optional[str] = Field(default=None, max_length=20)  # 연료
    status: Optional[str] = Field(default=None, max_length=20)  # VEHICLE_STATUS
    asset_id: Optional[str] = Field(default=None, max_length=50)  # 선택 관제 연결
    memo: Optional[str] = Field(default=None, max_length=255)


class ClientVehicleUpdate(BlankFKToNoneModel):
    """차량 마스터 부분 수정 — 전달된 필드만 반영(전 필드 optional)."""

    vehicle_no: Optional[str] = Field(default=None, min_length=1, max_length=30)
    client_id: Optional[str] = Field(default=None, max_length=50)
    operator_name: Optional[str] = Field(default=None, max_length=100)
    chassis_no: Optional[str] = Field(default=None, max_length=50)
    model_name: Optional[str] = Field(default=None, max_length=50)
    model_year: Optional[int] = Field(default=None, ge=0)
    registered_at: Optional[date] = None
    vehicle_class: Optional[str] = Field(default=None, max_length=50)
    length_mm: Optional[int] = Field(default=None, ge=0)
    width_mm: Optional[int] = Field(default=None, ge=0)
    height_mm: Optional[int] = Field(default=None, ge=0)
    gross_weight_kg: Optional[int] = Field(default=None, ge=0)
    seating_capacity: Optional[int] = Field(default=None, ge=0)
    fuel: Optional[str] = Field(default=None, max_length=20)
    status: Optional[str] = Field(default=None, max_length=20)
    asset_id: Optional[str] = Field(default=None, max_length=50)
    memo: Optional[str] = Field(default=None, max_length=255)


class ClientVehicleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    vehicle_id: str
    client_id: Optional[str] = None
    client_name: Optional[str] = None  # 운수사명(조인)
    operator_name: Optional[str] = None
    vehicle_no: Optional[str] = None
    region: Optional[str] = None
    chassis_no: Optional[str] = None
    model_name: Optional[str] = None
    model_year: Optional[int] = None
    registered_at: Optional[date] = None
    vehicle_class: Optional[str] = None
    length_mm: Optional[int] = None
    width_mm: Optional[int] = None
    height_mm: Optional[int] = None
    gross_weight_kg: Optional[int] = None
    seating_capacity: Optional[int] = None
    fuel: Optional[str] = None
    status: Optional[str] = None
    asset_id: Optional[str] = None
    memo: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ClientVehicleListItem(ClientVehicleOut):
    """고객사 상세 보유 차량 목록 항목 — 마스터 필드 + 감축사업 참여 구분(부록 M).

    participation은 ProjectVehicle이 이 마스터(client_vehicle_id)를 가리키는지 여부.
    참여 시 대표 1건의 사업·도입구분·잔여반영감축량·예상지급액을 함께 노출(전부 optional)."""

    participation: bool = False
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    introduction_type: Optional[str] = None
    effective_reduction: Optional[float] = None
    expected_payout: Optional[float] = None


class ClientVehicleListResponse(BaseModel):
    items: List[ClientVehicleListItem]
    total: int
    page: int
    page_size: int
    participating_count: int  # 해당 고객사 전체 기준(필터 무관)
    unassigned_count: int  # 해당 고객사 전체 기준(필터 무관)


class FleetImportResult(BaseModel):
    """전역 fleet 엑셀 업로드 결과 요약(부록 M)."""

    created: int = 0
    updated: int = 0
    client_matched: int = 0  # 업체명→운수사 매칭 성공 행
    linked_participation: int = 0  # ProjectVehicle.client_vehicle_id 세팅 건수
    introduction_derived: int = 0  # 도입구분 자동 판별 설정 건수(내연 fleet 대조)
    skipped: int = 0  # vehicle_no 없는 행 등


class FleetPreviewRow(BaseModel):
    """전역 fleet 미리보기 상세 행(부록 M) — '건너뜀' 행만 반환(페이로드 절감)."""

    row: int  # 엑셀 물리 행번호(1행 헤더, 데이터는 2행부터)
    vehicle_no: Optional[str] = None
    chassis_no: Optional[str] = None
    classification: str  # "신규"|"갱신"|"건너뜀"
    reason: Optional[str] = None  # 건너뜀 사유(예: "차량번호 없음"·"예시행")


class FleetPreviewResult(BaseModel):
    """전역 fleet 엑셀 dry-run 결과 — 실반영 없이 예측 집계(부록 M)."""

    total_rows: int = 0  # 처리 데이터 행 수(완전 빈 행 제외)
    created: int = 0  # 신규 예측
    updated: int = 0  # 갱신 예측
    skipped: int = 0  # 건너뜀(차량번호 없음·예시행 등)
    client_matched: int = 0  # 업체명→운수사 매칭 예측
    rows: List[FleetPreviewRow] = []  # '건너뜀' 행 상세만


class ProjectDetailOut(ProjectOut):
    """사업 상세 (SCR-06) — 개요 + 진행 단계 + 거래계약/원장 파생."""

    stages: List[ProjectStageOut] = []  # 진행 단계 타임라인(Phase 1)
    delayed_stage_count: int = 0  # 지연 단계 수(관찰용)
    vehicle_count: int = 0  # 참여 차량 수(Phase 2)
    total_reduction: float = 0  # 총 감축량(차량 연차 합의 합, Phase 2)
    # 거래계약 + 내부 차액 수익 파생(저장 없이 상세에서 계산, 내부 표시용)
    sales: List[ProjectSaleOut] = []  # 거래계약(매수자별 선물 판매) 목록
    sale_amount: Optional[float] = None  # 매출 Σ(판매단가×수량, 둘 다 입력된 계약만)
    payout_amount: Optional[float] = None  # 지급 Σ(차량 expected_payout, None 제외)
    margin_amount: Optional[float] = None  # 차액 = sale_amount − payout_amount(둘 다 있을 때만)
    margin_ratio: Optional[float] = None  # margin_amount/sale_amount × 100(%)
    # 회계 원장층 파생(부록 L.3) — 매입세금계산서·실발행액 기반 회계 체인(내부 표시용)
    product: Optional[float] = None  # 제품(총매입) = Σ 매입세금계산서 금액
    expected_payment: Optional[float] = None  # 예상지급액 = Σ 차량 expected_payout(전건 None이면 None)
    wip1: Optional[float] = None  # 미착품1(미승인 시 예상지급액)
    wip2: Optional[float] = None  # 미착품2(승인 시 trunc(예상지급액 − 제품))
    liability: Optional[float] = None  # 부채 = wip1 + wip2
    inventory: Optional[float] = None  # 재고자산 = 부채 + 제품
    payout_rate: Optional[float] = None  # 지급률 = round(제품/예상지급액, 3)
    sale_recognized: Optional[float] = None  # 매출인식 = trunc(Σ trunc(실발행액 × 지급률))
    gross_profit: Optional[float] = None  # 매출이익 = trunc(매출인식 − 제품)
    profit_rate: Optional[float] = None  # 이익률 = round(매출이익/매출인식, 3)
    ownership_total: Optional[float] = None  # 소유권비율 합(%)
    # 재고평가 파생(비영속 read-only, 증분3) — 후시보유분 × 현재시세. 저장 없음.
    current_market_rate: Optional[float] = None  # 현재 매출단가 시세(없으면 None)
    inventory_valuation: Optional[float] = None  # 재고평가액 = Σ(is_hold='Y' quantity) × 현재시세(원단위 반올림)
    # 예상수익 파생(비영속 read-only, B2) — Σ잔여반영감축량 × 직전 6개월 평균시세(원단위 절사)
    market_rate_avg6: Optional[float] = None  # 직전 6개월 평균 매출단가 시세(없으면 None)
    expected_revenue: Optional[float] = None  # 예상수익 = trunc(Σeff × 6개월평균시세), None 안전


# ---------------------------------------------------------------------------
# 포털 전용 뷰 (Phase 4 INC-4 / 부록 N.3 기밀 매트릭스)
#
# 원칙: 금지 필드를 스키마에 아예 선언하지 않아 서버가 원천 미포함(마스킹 아님).
# 어느 뷰도 원가와 매출을 동시에 담지 않는다(H.6). 내부 ProjectDetailOut·
# compute_accounting은 재사용/호출하지 않는다(별도 빌더 services/portal.py).
# ---------------------------------------------------------------------------
class PartnerPortalView(BaseModel):
    """운수사(파트너) 포털 뷰 — 자기 참여분만.

    매출·판매단가·마진·타 운수사 데이터 필드는 선언하지 않는다(원천 미포함).
    자기 수혜금액(자기 차량 expected_payout 합)만 노출하며 원가율 역산 소지가 없다.
    """

    project_id: str
    project_name: str
    project_status: str
    stages: List[ProjectStageOut] = []  # 진행 단계·지연(내부와 동일 산정)
    my_vehicle_count: int = 0  # 자기 운수사 참여 차량 수
    my_effective_reduction: Optional[float] = None  # 자기 운수사 잔여반영감축량 합(전건 None이면 None)
    my_expected_payout: Optional[float] = None  # 자기 수혜금액 = Σ 자기 차량 expected_payout(산정 전이면 None)


class InvestorPortalView(BaseModel):
    """투자/금융(매수자) 포털 뷰 — 프로젝트 총량·감축량(익명)·자기 계약만.

    예상지급액·원가·지급률·매출인식·매출이익·제품·미착품·마진 필드는 선언하지 않는다
    (자기 실발행액으로 원가율 역산 방지). operators_reduction은 식별정보 없이 익명 라벨.
    """

    project_id: str
    project_name: str
    project_status: str
    stages: List[ProjectStageOut] = []  # 진행 단계·지연
    operators_reduction: List[dict] = []  # 참여 운수사별 감축량(익명): {label, vehicle_count, effective_reduction}
    total_effective_reduction: Optional[float] = None  # 총 잔여반영감축량(전건 None이면 None)
    total_contract_revenue: Optional[float] = None  # 프로젝트 총 계약매출 gross(실발행액 우선, 없으면 단가×수량)
    my_contract: Optional[dict] = None  # 자기 매수자 계약: {quantity, gross_revenue, sale_unit_price, sale_invoice_amount}


# ---------------------------------------------------------------------------
# P1 — 활동 이력·이슈 (SCR-05 / 02)
# ---------------------------------------------------------------------------
class HistoryCreate(BlankFKToNoneModel):
    client_id: Optional[str] = Field(default=None, max_length=50)  # 미지정 고객 임시 이력 허용 (GAN E5)
    manager_id: Optional[str] = Field(default=None, max_length=50)  # 미지정 시 현재 사용자
    activity_date: datetime
    # activity_type은 공통 코드 마스터(ACTIVITY_TYPE)로 관리 → 라우터에서 검증
    activity_type: str = Field(min_length=1, max_length=20)
    retention_stage: Optional[str] = Field(default=None, max_length=20)
    # issue_status는 공통 코드 마스터(ISSUE_STATUS)로 관리 → 라우터에서 검증
    issue_status: Optional[str] = Field(default=None, min_length=1, max_length=20)
    priority: Optional[str] = Field(default=None, pattern="^(URGENT|NORMAL)$")
    due_date: Optional[date] = None
    next_action: Optional[str] = Field(default=None, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    content: Optional[str] = None
    main_needs: Optional[str] = Field(default=None, max_length=200)

    @field_validator("activity_date")
    @classmethod
    def _check_naive(cls, v):
        """벽시계 KST naive만 허용 (#6 P3) — Z·+09:00 접미사 422."""
        return reject_tz_aware(v)


class HistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    history_id: str
    client_id: Optional[str] = None
    client_name: Optional[str] = None
    manager_id: str
    manager_name: Optional[str] = None
    created_by: Optional[str] = None
    created_by_name: Optional[str] = None
    activity_date: datetime
    activity_type: str
    retention_stage: Optional[str] = None
    issue_status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[date] = None
    next_action: Optional[str] = None
    next_action_done: Optional[str] = None
    related_history_id: Optional[str] = None
    chat_thread_id: Optional[str] = None  # 상담 스레드에서 승격된 이슈(K3) — 원 스레드 링크
    title: str
    content: Optional[str] = None
    main_needs: Optional[str] = None
    is_auto: bool = False  # 보고서 발송·일정 완료 자동 적재 표식
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class HistoryListResponse(BaseModel):
    items: List[HistoryOut]
    total: int


class IssueStatusUpdate(BaseModel):
    """SCR-02 칸반 드래그 — 이슈 상태 변경."""

    issue_status: str = Field(min_length=1, max_length=20)
    comment: Optional[str] = None  # 상태 변경 사유(선택)


class CommentCreate(BaseModel):
    content: str = Field(min_length=1)
    comment_type: str = Field(default="COMMENT", pattern="^(COMMENT|STATUS_CHANGE|ASSIGN)$")


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    comment_id: str
    history_id: str
    manager_id: str
    manager_name: Optional[str] = None
    comment_type: Optional[str] = None
    content: Optional[str] = None
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# P1 — 일정 (SCR-11)
# ---------------------------------------------------------------------------
class ScheduleCreate(BlankFKToNoneModel):
    client_id: Optional[str] = Field(default=None, max_length=50)  # null = 내부 일정
    manager_id: Optional[str] = Field(default=None, max_length=50)  # 미지정 시 현재 사용자
    schedule_type: str = Field(pattern="^(MEETING|CALL|SITE_VISIT|REPORT_DUE|INTERNAL)$")
    title: str = Field(min_length=1, max_length=200)
    start_at: datetime
    end_at: Optional[datetime] = None
    location: Optional[str] = Field(default=None, max_length=200)
    memo: Optional[str] = None
    recur_rule: Optional[str] = Field(default=None, max_length=50)
    recur_until: Optional[date] = None

    @field_validator("start_at", "end_at")
    @classmethod
    def _check_naive(cls, v):
        """벽시계 KST naive만 허용 (#6 P3) — Z·+09:00 접미사 422."""
        return reject_tz_aware(v)

    @model_validator(mode="after")
    def _check_time_order(self):
        """일정 시간 역전 차단 (#3) — end_at이 start_at보다 빠르면 422."""
        if self.end_at is not None and self.end_at < self.start_at:
            raise ValueError("종료 시각이 시작 시각보다 빠릅니다")
        return self


class ScheduleUpdate(BlankFKToNoneModel):
    """일자 드래그 변경·완료 처리 — DONE 전환 시 활동 이력 자동 적재."""

    client_id: Optional[str] = Field(default=None, max_length=50)
    manager_id: Optional[str] = Field(default=None, max_length=50)
    schedule_type: Optional[str] = Field(
        default=None, pattern="^(MEETING|CALL|SITE_VISIT|REPORT_DUE|INTERNAL)$"
    )
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    location: Optional[str] = Field(default=None, max_length=200)
    memo: Optional[str] = None
    status: Optional[str] = Field(default=None, pattern="^(PLANNED|DONE|CANCELED)$")
    result_note: Optional[str] = None  # 완료 시 조치 결과 — 자동 이력 content로 기록

    @field_validator("start_at", "end_at")
    @classmethod
    def _check_naive(cls, v):
        """벽시계 KST naive만 허용 (#6 P3) — Z·+09:00 접미사 422."""
        return reject_tz_aware(v)

    @model_validator(mode="after")
    def _check_time_order(self):
        """일정 시간 역전 차단 (#3) — 둘 다 전달된 경우만(부분 수정은 라우터에서 최종 검증)."""
        if self.start_at is not None and self.end_at is not None and self.end_at < self.start_at:
            raise ValueError("종료 시각이 시작 시각보다 빠릅니다")
        return self


class ScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    schedule_id: str
    client_id: Optional[str] = None
    client_name: Optional[str] = None
    manager_id: str
    manager_name: Optional[str] = None
    schedule_type: str
    title: str
    start_at: datetime
    end_at: Optional[datetime] = None
    location: Optional[str] = None
    memo: Optional[str] = None
    status: Optional[str] = None
    recur_rule: Optional[str] = None
    recur_until: Optional[date] = None
    parent_schedule_id: Optional[str] = None
    history_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# P1 — 문서 (SCR-13)
# ---------------------------------------------------------------------------
class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    doc_id: str
    client_id: Optional[str] = None
    client_name: Optional[str] = None
    doc_type: str
    title: str
    file_url: str
    version: Optional[int] = None
    report_id: Optional[str] = None
    history_id: Optional[str] = None
    asset_id: Optional[str] = None
    uploaded_by: Optional[str] = None
    uploaded_by_name: Optional[str] = None
    created_at: Optional[datetime] = None


class DocumentListResponse(BaseModel):
    items: List[DocumentOut]
    total: int


# ---------------------------------------------------------------------------
# P1 — 월간 보고서 발송 (SCR-12)
# ---------------------------------------------------------------------------
class ReportSummary(BaseModel):
    """발송 현황 요약 바 — 대상 n개사 | 미착수·작성중·검토·발송승인·발송완료·확인·취소."""

    target: int = 0
    standby: int = 0
    writing: int = 0
    review: int = 0
    approved: int = 0
    sent: int = 0
    confirmed: int = 0
    canceled: int = 0


class ReportRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    report_id: str
    client_id: str
    client_name: Optional[str] = None
    client_type: Optional[str] = None
    period: str
    report_type: str
    status: str
    canceled_reason: Optional[str] = None
    due_date: Optional[date] = None
    sent_at: Optional[datetime] = None
    sent_channel: Optional[str] = None
    confirmed_at: Optional[datetime] = None
    confirm_basis: Optional[str] = None
    doc_id: Optional[str] = None
    pinned_doc_id: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    manager_id: Optional[str] = None
    manager_name: Optional[str] = None
    latest_doc: Optional[DocumentOut] = None  # 최신 파일 버전 표시
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ReportListResponse(BaseModel):
    period: str
    summary: ReportSummary
    items: List[ReportRow]


class ReportGenerateResponse(BaseModel):
    period: str
    created: int
    skipped: int
    message: str


class ReportStatusUpdate(BaseModel):
    status: str = Field(pattern="^(STANDBY|WRITING|REVIEW|APPROVED|SENT|CONFIRMED|CANCELED)$")
    confirm_basis: Optional[str] = Field(default=None, max_length=20)  # CONFIRMED — 회신메일/유선/열람 (GAN B11)
    canceled_reason: Optional[str] = Field(default=None, max_length=200)  # CANCELED 시 필수 (R3-3)


class ReportSendRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=200)  # 정정 재발송 사유
    # 발송 시 추가 첨부할 고객사 Dropbox 파일 경로(라이브 브라우즈 선택) — 해당 고객사 폴더 하위만 허용
    dropbox_attachment_paths: Optional[List[str]] = Field(default=None)


class ReportSendResponse(BaseModel):
    message: str
    report_id: str
    seq: int
    recipients: List[str]
    sent_at: datetime


class SendLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    send_id: str
    report_id: str
    seq: int
    sent_doc_id: Optional[str] = None
    recipients: Optional[str] = None
    channel: Optional[str] = None
    result: Optional[str] = None
    confirmed_at: Optional[datetime] = None
    confirm_basis: Optional[str] = None
    sent_by: Optional[str] = None
    sent_by_name: Optional[str] = None
    reason: Optional[str] = None
    created_at: Optional[datetime] = None


class ReportDetailOut(ReportRow):
    """행 확장 — 버전 히스토리·발송 기록·코멘트(모델에 보고서 코멘트 테이블 없음 — 빈 배열)."""

    documents: List[DocumentOut] = []
    send_logs: List[SendLogOut] = []
    comments: List[CommentOut] = []


# ---------------------------------------------------------------------------
# P3 — 카카오 채널 연동 (SCR-08 / CR-3)
# ---------------------------------------------------------------------------
class SuggestedClient(BaseModel):
    """전화번호 대조로 나온 매핑 후보 고객사 — 승인 보조(확정은 사람, CR-3)."""

    client_id: str
    company_name: str
    matched_field: str  # '주 담당 전화' | '대표 전화'


class KakaoContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    contact_id: str
    kakao_user_key: str
    client_id: Optional[str] = None
    client_name: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    contact_role: Optional[str] = None
    status: str
    requested_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    approved_by_name: Optional[str] = None
    approved_at: Optional[datetime] = None
    memo: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # 전화번호 일치 매핑 후보(PENDING+전화 있을 때만) — 승인 화면 [이 고객사로 승인] 보조
    suggested_clients: List[SuggestedClient] = []


class KakaoContactListResponse(BaseModel):
    items: List[KakaoContactOut]
    total: int


class KakaoContactUpdate(BlankFKToNoneModel):
    """연락처 승인 게이트 (CR-3) — APPROVED는 client_id 매핑 필수. MANAGER 이상."""

    status: str = Field(pattern="^(PENDING|APPROVED|REJECTED|BLOCKED)$")
    client_id: Optional[str] = Field(default=None, max_length=50)
    name: Optional[str] = Field(default=None, max_length=50)
    phone: Optional[str] = Field(default=None, max_length=20)
    contact_role: Optional[str] = Field(default=None, pattern="^(REPRESENTATIVE|CONTACT)$")
    memo: Optional[str] = Field(default=None, max_length=200)


class KakaoNotifyRequest(BaseModel):
    """수동 알림톡 발송 — 템플릿 미지정 시 KAKAO_TEMPLATE_REPLY 사용."""

    to: str = Field(min_length=9, max_length=20, description="수신자 휴대폰 번호")
    template_code: Optional[str] = None
    variables: dict = {}
    buttons: Optional[List[dict]] = None


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message_id: str
    thread_id: str
    sender_type: str
    sender_id: Optional[str] = None
    sender_name: Optional[str] = None
    content: Optional[str] = None
    created_at: Optional[datetime] = None


class ChatThreadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    thread_id: str
    client_id: Optional[str] = None
    client_name: Optional[str] = None
    kakao_contact_id: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    mode: Optional[str] = None
    status: Optional[str] = None
    last_message_at: Optional[datetime] = None
    last_message_preview: Optional[str] = None
    assigned_manager_id: Optional[str] = None
    assigned_manager_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ChatThreadListResponse(BaseModel):
    items: List[ChatThreadOut]
    total: int


class ChatReplyRequest(BaseModel):
    content: str = Field(min_length=1, max_length=1000)


class ChatReplyResponse(BaseModel):
    """delivery: SENT(Event API 발송 성공) / FAILED(발송 실패 — 메시지는 적재됨)
    / NOT_CONFIGURED(Event API 미설정 — 메시지는 적재됨)."""

    delivery: str
    message: ChatMessageOut


class ChatThreadUpdate(BlankFKToNoneModel):
    """모드 전환·담당 배정·종료 — CLOSED 전환 시 대화 요약을 활동 이력(KAKAO)으로 적재."""

    mode: Optional[str] = Field(default=None, pattern="^(AI|HUMAN)$")
    status: Optional[str] = Field(default=None, pattern="^(OPEN|WAITING|CLOSED)$")
    assigned_manager_id: Optional[str] = None


class ChatBadgeResponse(BaseModel):
    waiting: int


# ---------------------------------------------------------------------------
# P1 — 대시보드 (SCR-01)
# ---------------------------------------------------------------------------
class DashboardKpi(BaseModel):
    total_clients: int  # 관리 고객사 (ACTIVE)
    client_delta: int  # 이번 달 신규(증감)
    report_target: int  # 당월 보고서 대상 m
    report_sent: int  # 당월 발송 완료 n (SENT+CONFIRMED)
    urgent_open_issues: int  # 미처리 긴급 이슈
    contract_hold_clients: int  # 계약 검토·협의 중 (HOLD)


class DashboardStats(BaseModel):
    period: str
    kpi: DashboardKpi
    recent_activities: List[HistoryOut]
    open_issues: List[HistoryOut]


# 운수사 계약대수 현황 섹션(F4) — 최신 월 집계 + 전월 대비
class FleetDistItem(BaseModel):
    key: str  # 지역(조합) 또는 업종 코드
    license: int = 0
    electric: int = 0


class DashboardFleet(BaseModel):
    period: Optional[str] = None  # 데이터 있는 최신 월
    prev_period: Optional[str] = None
    companies: int = 0  # 최신 월 합산 행 수(운수사 스냅샷)
    matched_companies: int = 0  # 고객사 연결된 수
    total_license: int = 0
    total_count: int = 0
    total_electric: int = 0
    ev_share: float = 0.0  # 전기 비중(%)
    ev_delta: int = 0  # 전월 대비 전기 증감
    biz_target: int = 0  # 대상여부=사업대상(BIZ)
    reg_target: int = 0  # 대상여부=규제대상(REG)
    contracted: int = 0  # 계약여부 Y
    uncontracted: int = 0  # 계약여부 N/미지정
    by_industry: List[FleetDistItem] = []
    by_region: List[FleetDistItem] = []


# 지역별 통계표(F6) — 현황 탭 6표 재현
class FleetTableRow(BaseModel):
    region: str
    c1: int = 0
    c2: int = 0
    c3: int = 0


class FleetTable(BaseModel):
    key: str  # T1~T6
    title: str
    basis: str  # 'license'(대수) | 'count'(업체수)
    columns: List[str]  # 3개 열 라벨
    total: FleetTableRow  # 전국 합계
    rows: List[FleetTableRow]  # 지역별


class DashboardFleetTables(BaseModel):
    period: Optional[str] = None
    tables: List[FleetTable] = []


# ---------------------------------------------------------------------------
# 시스템 설정 (SCR-14 설정 탭 — tb_config, ADMIN 전용 §10.1)
# ---------------------------------------------------------------------------
class ConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    config_key: str
    config_value: Optional[str] = None  # JSON 문자열
    description: Optional[str] = None
    updated_by: Optional[str] = None
    updated_by_name: Optional[str] = None
    updated_at: Optional[datetime] = None
    is_default: bool = False  # True = DB 미저장 — 코드 기본값(미저장) 표시


class ConfigUpdate(BaseModel):
    """tb_config 값 변경 — config_value는 JSON 문자열(파싱 검증)."""

    config_value: str = Field(min_length=1)
    description: Optional[str] = None


class ConfigHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    history_id: str
    config_key: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    updated_by: Optional[str] = None
    updated_by_name: Optional[str] = None
    created_at: Optional[datetime] = None


class ConfigHistoryListResponse(BaseModel):
    items: List[ConfigHistoryOut]
    total: int


# ---------------------------------------------------------------------------
# 공통 코드 마스터 (SCR-14 공통 코드 관리 — tb_code)
# ---------------------------------------------------------------------------
class CodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code_id: str
    category: str
    code: str
    label: str
    color: Optional[str] = None  # 시맨틱 팔레트명(emerald/amber/rose/...)
    extra: Optional[str] = None  # 부가값 — AGENCY는 기본 접속 URL
    sort_order: int = 0
    active: str = "Y"
    is_system: str = "N"
    is_locked: bool = False  # 시스템 로직이 참조하는 코드 — 삭제·비활성 불가(라벨/색상만 수정)
    usage_count: Optional[int] = None  # 이 코드를 사용 중인 레코드 수(삭제 가능 판단용)


class CodeCreate(BaseModel):
    category: str = Field(min_length=1, max_length=40)
    # 영문/숫자/_ 권장이나 한글 코드 허용(감축사업 진행상태·대상 기관은 한글 저장값 유지)
    code: str = Field(min_length=1, max_length=20, pattern="^[A-Za-z0-9_가-힣]+$")  # 소비 컬럼 String(20) 정합 (DB 정밀검사 F1)
    label: str = Field(min_length=1, max_length=100)
    color: Optional[str] = Field(default=None, max_length=20)
    extra: Optional[str] = Field(default=None, max_length=255)
    sort_order: int = 0


class CodeUpdate(BaseModel):
    # code(코드값)·category는 불변 — label·색상·부가값·정렬·활성만 수정 가능
    label: Optional[str] = Field(default=None, min_length=1, max_length=100)
    color: Optional[str] = Field(default=None, max_length=20)
    extra: Optional[str] = Field(default=None, max_length=255)
    sort_order: Optional[int] = None
    active: Optional[str] = Field(default=None, pattern="^[YN]$")


# ---------------------------------------------------------------------------
# 연동 설정 (SCR-14 연동 탭 — tb_config "integration.*", ADMIN 전용)
# ---------------------------------------------------------------------------
class IntegrationFieldOut(BaseModel):
    """연동 필드 상태 — 시크릿 값 자체는 어떤 응답에도 포함하지 않는다 (R2-E6)."""

    key: str
    label: str
    secret: bool
    required: bool
    configured: bool
    source: Optional[str] = None  # "db" | "env" | None


class IntegrationOut(BaseModel):
    name: str
    label: str
    fields: List[IntegrationFieldOut]
    webhook_url: Optional[str] = None  # kakao_bot 전용 — 시크릿 마스킹 표시용


class IntegrationListResponse(BaseModel):
    items: List[IntegrationOut]


class IntegrationUpdate(BaseModel):
    """전달된 키만 갱신 — null/빈 문자열 = 삭제, 미전달 = 유지."""

    values: dict  # {ENV_KEY: value | null}


class IntegrationTestOut(BaseModel):
    ok: bool
    message: str


class IntegrationWebhookUrlOut(BaseModel):
    """오픈빌더 등록용 전체 웹훅 URL — ADMIN 전용, 열람 시 INTEGRATION_REVEAL 감사 기록."""

    url: str


class DropboxAuthorizeUrlOut(BaseModel):
    url: str


class DropboxOAuthExchangeRequest(BaseModel):
    code: str = Field(min_length=1)


# ---------------------------------------------------------------------------
# 감사 로그 (SCR-14 감사 로그 탭 — tb_audit_log, ADMIN 전용)
# ---------------------------------------------------------------------------
class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    log_id: str
    actor_id: str
    actor_name: Optional[str] = None
    action: str
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    target_name: Optional[str] = None  # 대상 이름(고객사명·사용자명 등) — UUID 대신 표시용
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    created_at: Optional[datetime] = None


class AuditLogListResponse(BaseModel):
    items: List[AuditLogOut]
    total: int


# ---------------------------------------------------------------------------
# P3 — 데이터베이스 백업·복구 (SCR-14, ADMIN 전용)
# ---------------------------------------------------------------------------
class BackupRunOut(BaseModel):
    backup_run_id: str
    backup_type: Optional[str] = None    # AUTOMATED / ON_DEMAND
    status: Optional[str] = None         # SUCCESSFUL / FAILED / RUNNING
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    description: Optional[str] = None


class BackupListResponse(BaseModel):
    policy: dict                         # {schedule, retention_days}
    items: List[BackupRunOut]


class BackupRestoreRequest(BaseModel):
    """복구 확인 — confirm에 '복구'를 입력해야 실행."""

    confirm: str = Field(min_length=1, max_length=10)
    backup_date: Optional[str] = None    # 감사 로그 표기용


class BackupOperationOut(BaseModel):
    operation_id: str
    status: str
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# 배치 — 공공기관 계정 월초 점검 (routers/batch.py)
# ---------------------------------------------------------------------------
class AccountCheckResponse(BaseModel):
    period: str
    targets: int
    created: int
    skipped: int
    unreachable: int


# ---------------------------------------------------------------------------
# 배치 — 보고서 자동 발송 (routers/batch.py, POST /batch/report-send)
# ---------------------------------------------------------------------------
class ReportSendBatchDetail(BaseModel):
    report_id: str
    client_name: Optional[str] = None
    result: str  # SENT | FAIL
    detail: Optional[str] = None  # 실패 사유 (SendPrecondition detail 등)


class ReportSendBatchResponse(BaseModel):
    period: str  # 발송 대상 기간 (기본: 전월)
    generated_created: int  # 당월 대상 자동 생성 — 신규
    generated_skipped: int  # 당월 대상 자동 생성 — 기존 유지
    targets: int  # 발송 대상(APPROVED) 건수
    sent: int
    failed: int
    details: List[ReportSendBatchDetail] = []


class ReportSendPreviewItem(BaseModel):
    """일괄 발송 미리보기 항목 (발송 없이 대상 1건을 사전 점검)."""

    report_id: str
    client_name: Optional[str] = None
    report_type: str  # 보고서 유형(코드)
    period: str  # 대상 기간 YYYY-MM
    filename: Optional[str] = None  # 실제 발송될 첨부파일명(고정본 우선, 없으면 최신본)
    recipients: int = 0  # TO 수신자 수(폴백 포함)
    ready: bool  # 발송 가능 여부(파일·수신자 충족)
    issue: Optional[str] = None  # 발송 불가 사유(ready=False일 때)


class ReportSendPreviewResponse(BaseModel):
    """일괄 발송 미리보기 — 대상 기간 APPROVED 전건의 발송 전 점검 결과(읽기 전용)."""

    period: str  # 발송 대상 기간 (기본: 전월)
    total: int  # 발송 대상(APPROVED) 건수
    ready_count: int  # 발송 가능 건수
    blocked_count: int  # 확인 필요(발송 불가) 건수
    items: List[ReportSendPreviewItem] = []


class DropboxProvisionResponse(BaseModel):
    """고객사 Dropbox 폴더 백필 결과 (POST /batch/provision-dropbox-folders)."""

    total: int  # dropbox_folder 없던 대상 고객사 수(이번 판정 시점)
    provisioned: int  # 폴더 생성 성공
    failed: int  # 생성 실패(재실행으로 재시도 가능)
    remaining: int = 0  # 배치 상한(limit) 초과로 다음 호출에 남은 대상 수


class ReconcilePreviewItem(BaseModel):
    """폴더명 규칙 교정 미리보기 항목 — 고객사 1건의 현재/제안 경로·판정(읽기 전용)."""

    client_id: str
    company_name: str
    current_path: str  # 현재 dropbox_folder(정규화)
    proposed_path: str  # 현재 규칙으로 계산한 목표 경로(정규화)
    action: str  # skip_match | move | conflict
    reason: Optional[str] = None  # root_changed | name_changed | null (표시용)


class ReconcilePreviewResponse(BaseModel):
    """폴더명 규칙 교정 미리보기 — 전 대상 판정 요약(이동/생성/삭제 없음)."""

    total: int  # 판정 대상(dropbox_folder 있는 고객사) 수
    move_count: int
    conflict_count: int
    skip_count: int
    items: List[ReconcilePreviewItem] = []


class ReconcileApplyDetail(BaseModel):
    """폴더명 규칙 교정 적용 결과 — 이동 시도 1건."""

    client_id: str
    from_path: str
    to_path: str
    result: str  # moved | conflict | failed | adopted(원본없음·목적지채택) | recreated(재생성)


class ReconcileApplyResponse(BaseModel):
    """폴더명 규칙 교정 적용 결과 — move 대상만 이동(멱등·실패 격리)."""

    total_candidates: int  # 재계산 시점의 move 대상 수
    moved: int
    conflicts: int
    failed: int
    recovered: int = 0  # 원본 없음 복구(adopted+recreated)
    remaining: int = 0  # 배치 상한(limit) 초과로 다음 호출에 남은 move 대상 수
    details: List[ReconcileApplyDetail] = []


class DropboxEntry(BaseModel):
    """Dropbox 폴더 항목 (조회 — GET /clients/{id}/dropbox/tree)."""

    name: str
    path_display: str
    is_dir: bool
    size: Optional[int] = None
    modified: Optional[str] = None


class DropboxTreeResponse(BaseModel):
    path: str  # 현재 조회한 폴더 경로(정규화)
    entries: List[DropboxEntry] = []


class DropboxFileLinkOut(BaseModel):
    """Dropbox 파일 임시 열람 링크 — 문서 아카이브 'Dropbox 폴더 보기' 파일 열람용."""

    url: str  # 4시간 유효 임시 다운로드 URL


# ---------------------------------------------------------------------------
# 세그먼트 보고서 발송 (SCR-12 확장 — tb_segment / routers/segments.py)
# ---------------------------------------------------------------------------
class SegmentCriteria(BaseModel):
    """세그먼트 조건 — 축 간 AND, 축 내 IN(OR). 미지원 키는 422(extra=forbid).

    코드 축(client_type 등) 값의 유효성은 라우터에서 공통 코드 마스터로 검증.
    """

    model_config = ConfigDict(extra="forbid")

    region: Optional[List[str]] = None
    client_type: Optional[List[str]] = None
    contract_status: Optional[List[str]] = None
    asset_group: Optional[List[str]] = None


def _parse_criteria_json(v):
    """DB Text(JSON 문자열) → dict — from_attributes 직렬화용. 파싱 실패 시 빈 조건.

    은퇴한 축(예: 레거시 settlement_status)이 저장분에 남아 있어도 로드가 깨지지
    않도록 SegmentCriteria가 아는 키만 남긴다(extra=forbid 방어).
    """
    if isinstance(v, str):
        try:
            parsed = json.loads(v) if v.strip() else {}
        except ValueError:
            return {}
    else:
        parsed = v if v is not None else {}
    if isinstance(parsed, dict):
        return {k: val for k, val in parsed.items() if k in SegmentCriteria.model_fields}
    return {}


class SegmentIn(BlankFKToNoneModel):
    """세그먼트 생성 — criteria는 라우터에서 검증 후 JSON 문자열로 저장."""

    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=200)
    criteria: SegmentCriteria = Field(default_factory=SegmentCriteria)
    manager_id: Optional[str] = None
    # 세그먼트 기본 메일 템플릿 — null이면 발송 시 직접 입력/전역 기본
    mail_subject: Optional[str] = Field(default=None, max_length=200)
    mail_body: Optional[str] = None


class SegmentUpdate(BlankFKToNoneModel):
    """세그먼트 수정 — 전달된 필드만 반영. active=N은 soft 삭제와 동일."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=200)
    criteria: Optional[SegmentCriteria] = None
    manager_id: Optional[str] = None
    mail_subject: Optional[str] = Field(default=None, max_length=200)
    mail_body: Optional[str] = None
    active: Optional[str] = Field(default=None, pattern="^[YN]$")


class SegmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    segment_id: str
    name: str
    description: Optional[str] = None
    criteria: SegmentCriteria = Field(default_factory=SegmentCriteria)
    active: Optional[str] = None
    manager_id: Optional[str] = None
    manager_name: Optional[str] = None
    mail_subject: Optional[str] = None
    mail_body: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("criteria", mode="before")
    @classmethod
    def _coerce_criteria(cls, v):
        return _parse_criteria_json(v)


class SegmentPreviewRequest(BaseModel):
    criteria: SegmentCriteria = Field(default_factory=SegmentCriteria)


class SegmentPreviewItem(BaseModel):
    client_id: str
    company_name: str
    client_type: Optional[str] = None
    region: Optional[str] = None
    # 계약 상태 — 종료(END)·보류(HOLD) 고객사 오발송 예방 배지용
    contract_status: Optional[str] = None
    # 수신 가능 — 공통 수신자(sub_id IS NULL) 존재 or 주 담당자 이메일 보유
    can_receive: bool = False


class SegmentPreviewResponse(BaseModel):
    total: int
    items: List[SegmentPreviewItem]


class SegmentFacetsOut(BaseModel):
    """조건 축 선택지 — region만 서버 제공(나머지 축은 /codes·/projects 재사용)."""

    regions: List[str]


class SegmentSendOut(BaseModel):
    """발송 실행 이력 행 (B5 발송·이력 조회용) — 스냅샷은 원문 그대로 노출."""

    model_config = ConfigDict(from_attributes=True)

    send_id: str
    segment_id: Optional[str] = None
    criteria_snapshot: Optional[str] = None  # 발송 시점 조건 JSON
    doc_ids: Optional[str] = None  # JSON 배열 문자열
    subject: Optional[str] = None
    body: Optional[str] = None
    target_count: int = 0
    sent_count: int = 0
    failed_count: int = 0
    sent_by: Optional[str] = None
    sent_by_name: Optional[str] = None
    created_at: Optional[datetime] = None


class SegmentSendRequest(BaseModel):
    """세그먼트 발송 요청 (B5) — doc_ids 또는 dropbox_paths 중 최소 1개(라우터에서 검증).

    subject/body 미지정 시 세그먼트 오버라이드 → tb_config report_mail_* → 코드 기본값.
    criteria는 즉석 발송(POST /segments/send)에서만 필수 — 저장 세그먼트 발송은 저장분 사용.
    dropbox_paths: 공용 발송자료(공용_발송자료) 폴더에서 고른 공통 첨부 파일 경로.
    """

    doc_ids: List[str] = Field(default_factory=list)
    dropbox_paths: Optional[List[str]] = None
    # mail-merge: 각 수신 고객사 자신의 이 구분폴더(CLIENT_FOLDER 코드)에서 최신 1개를 개별 첨부
    merge_folder_code: Optional[str] = None
    merge_name_contains: Optional[str] = Field(default=None, max_length=100)
    subject: Optional[str] = Field(default=None, max_length=200)
    body: Optional[str] = None
    criteria: Optional[SegmentCriteria] = None


class SegmentSendDetail(BaseModel):
    """발송 실행 결과 고객사별 상세 — SUCCESS/FAIL(사유)."""

    client_id: str
    client_name: Optional[str] = None
    result: str  # SUCCESS/FAIL
    reason: Optional[str] = None


class SegmentSendResponse(BaseModel):
    """발송 실행 응답 — 카운트 요약 + 고객사별 결과."""

    send_id: str
    target_count: int
    sent_count: int
    failed_count: int
    details: List[SegmentSendDetail] = []


class SegmentSendLogOut(BaseModel):
    """발송 이력 상세의 고객사별 로그 행 (tb_segment_send_log)."""

    model_config = ConfigDict(from_attributes=True)

    log_id: str
    client_id: str
    client_name: Optional[str] = None
    recipients: Optional[str] = None  # 수신자 스냅샷 JSON
    channel: Optional[str] = None
    result: Optional[str] = None
    reason: Optional[str] = None
    created_at: Optional[datetime] = None


class SegmentSendDetailOut(SegmentSendOut):
    """발송 이력 상세 — 실행 행 + 고객사별 로그 목록."""

    logs: List[SegmentSendLogOut] = []


# ---------------------------------------------------------------------------
# P1-D — 활동 이력 제한적 수정 (기록 불변 원칙의 예외 2필드)
# ---------------------------------------------------------------------------
class HistoryClientLink(BaseModel):
    """미상 고객 이력의 사후 고객사 연결 — client_id가 null인 이력만 허용."""

    client_id: str = Field(min_length=1, max_length=50)


class HistoryManagerUpdate(BlankFKToNoneModel):
    """이슈 담당자 인계 — ISSUE 유형 전용, ASSIGN 코멘트·감사로 흔적."""

    manager_id: str = Field(min_length=1, max_length=50)


# ---------------------------------------------------------------------------
# P1-F — 보고서 발송 고정본 지정 (SCR-12, R2-B4)
# ---------------------------------------------------------------------------
class ReportPinUpdate(BlankFKToNoneModel):
    """발송 고정본 지정/해제 요청 — doc_id가 None이면 고정 해제(최신본 발송 복귀)."""

    doc_id: Optional[str] = None


# ---------------------------------------------------------------------------
# 엑셀 일괄 등록 (SCR-03/04 imports) — 규격 원천은 services/import_spec.py
# ---------------------------------------------------------------------------
class ImportColumnOut(BaseModel):
    """컬럼 안내 — 프론트 업로드 가이드·양식 설명용 (import_spec에서 파생)."""

    field: str
    label: str
    required: bool = False
    code_category: Optional[str] = None  # tb_code 카테고리 (라벨/코드 양방향 수용)
    resolver: Optional[str] = None       # user_by_name/client_by_name — 이름으로 입력
    yn: bool = False                     # Y/N 컬럼
    allowed_values: Optional[List[str]] = None  # 고정값 컬럼(인증 방식 등) 허용 표기
    example: Optional[str] = None


class ImportSpecOut(BaseModel):
    entity: str
    label: str
    max_rows: int
    filename: str
    columns: List[ImportColumnOut]


class ImportRowResult(BaseModel):
    """행 단위 검증 결과 — row는 엑셀 실제 행 번호(헤더=1, 데이터 2부터)."""

    row: int
    status: str  # OK/ERROR
    data: Dict[str, Optional[str]] = {}  # 라벨 → 정규화된 저장 예정 값(표시용)
    errors: List[str] = []
    warnings: List[str] = []


class ImportPreviewOut(BaseModel):
    """미리보기(DB 무변경) — commit 전 전 행 검증 결과."""

    entity: str
    total_rows: int
    valid_rows: int
    error_rows: int
    unknown_columns: List[str] = []  # 스펙에 없는 헤더(무시됨) — 경고
    warnings: List[str] = []  # 파일 수준 안내 (예: 예시 행 스킵)
    rows: List[ImportRowResult] = []


class ImportCommitOut(BaseModel):
    """반영 결과 — 유효 행만 생성(부분 반영), 오류 행은 건너뜀."""

    entity: str
    created: int
    skipped: int
    updated: int = 0  # upsert(운수사 정보 정본)에서 기존 건 갱신 수
    errors: List[ImportRowResult] = []


# ── 운수사 계약대수 현황(F2/F3) ──────────────────────────────────────────
class FleetStatusItem(BaseModel):
    """업로드 미리보기 항목 — (고객사×월) 합산 결과 1건."""

    region: Optional[str] = None
    industry: Optional[str] = None
    company_name: Optional[str] = None
    period: Optional[str] = None
    matched: bool = False
    is_update: bool = False
    matched_client_id: Optional[str] = None
    matched_client_name: Optional[str] = None
    license: int = 0
    total: int = 0
    diesel: int = 0
    cng: int = 0
    hybrid: int = 0
    electric: int = 0
    hydrogen: int = 0


class FleetStatusPreviewOut(BaseModel):
    period: str
    total_rows: int
    aggregated: int
    matched: int
    unmatched: int
    items: List[FleetStatusItem] = []


class FleetStatusCommitOut(BaseModel):
    period: str
    total_rows: int
    aggregated: int
    created: int
    updated: int
    matched: int
    unmatched: int
    # 현황 탭 분류 반영(F6) — 현황 탭이 있을 때만(단일 원본 탭이면 0)
    mgmt_rows: int = 0
    mgmt_matched: int = 0
    mgmt_updated: int = 0
    mgmt_created: int = 0


class FleetStatusTrendItem(BaseModel):
    """고객사 상세 '현황' 탭 — 월별 대수 스냅샷 1건."""

    period: str
    license_count: Optional[int] = None
    total_count: Optional[int] = None
    diesel: Optional[int] = None
    cng: Optional[int] = None
    hybrid: Optional[int] = None
    electric: Optional[int] = None
    hydrogen: Optional[int] = None
    region: Optional[str] = None
    industry: Optional[str] = None


class FleetMgmtIn(BaseModel):
    """수작업 관리 저장 — 대상·계약·조합·규제 분류(코드값, 업로드 무영향)."""

    target_type: Optional[str] = None  # FLEET_TARGET: BIZ/REG
    contract_status: Optional[str] = None  # FLEET_CONTRACT: DONE/NONE/REVIEW/EXCLUDED
    union_contract: Optional[str] = None  # FLEET_UNION: REP/MOU
    regulated_type: Optional[str] = None  # FLEET_REGULATED: ALLOC/GOAL/PUBLIC
    memo: Optional[str] = None


class FleetMgmtOut(FleetMgmtIn):
    client_id: str


class FleetClientStatusOut(BaseModel):
    """현황 탭 응답 — 월별 추이 + 수작업 관리."""

    client_id: str
    trend: List[FleetStatusTrendItem] = []
    mgmt: Optional[FleetMgmtOut] = None


# ── 접근 그룹 관리(G3) ──────────────────────────────────────────────────
class AccessGroupIn(BaseModel):
    name: str
    dept_code: Optional[str] = None  # 공통코드 DEPT — 지정 시 표시명이 코드 라벨을 따름
    home_path: Optional[str] = None
    memo: Optional[str] = None
    menus: List[str] = []


class AccessGroupOut(BaseModel):
    group_id: str
    name: str  # dept_code 지정 시 공통코드(DEPT) 라벨로 라이브 해석된 표시명
    dept_code: Optional[str] = None
    home_path: Optional[str] = None
    is_default: bool = False
    memo: Optional[str] = None
    menus: List[str] = []
    member_ids: List[str] = []


class AccessGroupMeta(BaseModel):
    menu_keys: List[str] = []
    mode: str = "off"
    modes: List[str] = []


class AccessModeIn(BaseModel):
    mode: str


class UserGroupsIn(BaseModel):
    group_ids: List[str] = []


# ── 포털 P1 — 운수사(PARTNER) 확장 ──────────────────────────────────────
class PortalReportItem(BaseModel):
    report_id: str
    period: str
    report_type: str
    status: str  # SENT/CONFIRMED
    sent_at: Optional[datetime] = None
    has_file: bool = False


class PortalSettlementItem(BaseModel):
    settlement_id: str
    project_name: Optional[str] = None
    period: Optional[str] = None
    status: str  # SETTLEMENT_STATUS 코드
    confirmed_amount: Optional[float] = None
    vehicle_count: Optional[int] = None
    confirmed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    paid_amount: Optional[float] = None


class ExternalAccountPreview(BaseModel):
    """발급 전 미리보기 — 이 외부 계정이 포털에서 보게 될 내용(관리자 검증용, read-only)."""

    user_id: str
    name: Optional[str] = None
    email: str
    role: str  # PARTNER/INVESTOR
    status: str
    org_name: Optional[str] = None
    projects: List[dict] = []  # 포털 /projects와 동일 형태
    fleet_status: List[FleetStatusTrendItem] = []  # PARTNER만
    reports: List[PortalReportItem] = []  # PARTNER만
    settlements: List[PortalSettlementItem] = []  # PARTNER만
    warnings: List[str] = []  # 미연결·비활성 등 발급 전 확인 사항


class ClientOptionOut(BaseModel):
    """드롭다운·이름 맵용 경량 고객사 옵션 — 집계 없는 최소 필드(전건)."""

    client_id: str
    client_type: str
    company_name: str
    region: Optional[str] = None
    biz_reg_no: Optional[str] = None
    contract_status: Optional[str] = None
    # 주 담당자 연락처 — 포털 계정 발급 자동 채움 등 폼 프리필용
    main_contact_name: Optional[str] = None
    main_contact_email: Optional[str] = None
    main_contact_phone: Optional[str] = None
