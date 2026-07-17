"""Pydantic 스키마 — P0(auth·users·health) + P1(고객사·이력·일정·보고서·문서·대시보드)
+ P2(자산·감축 사업·정산) + P3(카카오 채널·채팅 상담) + 세그먼트 발송."""

import json
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# 공통
# ---------------------------------------------------------------------------
class MessageResponse(BaseModel):
    message: str


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


class UserApproveRequest(BaseModel):
    """가입 승인 (PENDING→ACTIVE) — role 지정 (CR-1)."""

    role: str = Field(default="STAFF", pattern="^(ADMIN|MANAGER|STAFF)$")


class UserRoleRequest(BaseModel):
    role: str = Field(pattern="^(ADMIN|MANAGER|STAFF)$")


class UserCreateRequest(BaseModel):
    """관리자 직접 계정 생성 — 즉시 ACTIVE (최초 로그인 시 PIN 설정)."""

    email: str = Field(min_length=3, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    name: Optional[str] = Field(default=None, max_length=50)
    position: Optional[str] = Field(default=None, max_length=50)
    role: str = Field(default="STAFF", pattern="^(ADMIN|MANAGER|STAFF)$")


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
    client_type: str = Field(min_length=1, max_length=40)
    company_name: str = Field(min_length=1, max_length=100)
    biz_reg_no: Optional[str] = None
    region: Optional[str] = None
    address: Optional[str] = None
    ceo_name: Optional[str] = None
    ceo_contact_phone: Optional[str] = None
    ceo_contact_email: Optional[str] = None
    main_contact_name: Optional[str] = None
    main_contact_phone: Optional[str] = None
    main_contact_email: Optional[str] = None
    # contract_status는 공통 코드 마스터(CONTRACT_STATUS)로 관리 → 라우터에서 검증
    contract_status: str = Field(default="ACTIVE", min_length=1, max_length=40)
    contract_date: Optional[datetime] = None
    keyman: Optional[str] = None
    manager_id: Optional[str] = None
    report_yn: str = Field(default="N", pattern="^[YN]$")
    lat: Optional[float] = None
    lng: Optional[float] = None
    subscription: Optional[ReportSubscriptionIn] = None  # 월간 보고서 설정


class ClientUpdate(BaseModel):
    client_type: Optional[str] = Field(default=None, min_length=1, max_length=40)
    company_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    biz_reg_no: Optional[str] = None
    region: Optional[str] = None
    address: Optional[str] = None
    ceo_name: Optional[str] = None
    ceo_contact_phone: Optional[str] = None
    ceo_contact_email: Optional[str] = None
    main_contact_name: Optional[str] = None
    main_contact_phone: Optional[str] = None
    main_contact_email: Optional[str] = None
    contract_status: Optional[str] = Field(default=None, min_length=1, max_length=40)
    contract_date: Optional[datetime] = None
    keyman: Optional[str] = None
    manager_id: Optional[str] = None
    report_yn: Optional[str] = Field(default=None, pattern="^[YN]$")
    lat: Optional[float] = None
    lng: Optional[float] = None
    subscription: Optional[ReportSubscriptionIn] = None


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
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ClientListItem(ClientOut):
    """목록 행 — 최근 활동 일시 + 이번 달 보고서 상태 미니 배지 + 성공 보수율(🔒 프론트 마스킹)."""

    last_activity_at: Optional[datetime] = None
    report_status_this_month: Optional[str] = None
    success_fee_rate: Optional[float] = None


class ClientListResponse(BaseModel):
    items: List[ClientListItem]
    total: int


class ClientDetailOut(ClientOut):
    subscriptions: List[ReportSubscriptionOut] = []


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
class AssetCreate(BaseModel):
    """자산 등록 — auth_value(평문 인증정보)는 서버 AES-256-GCM 암호화 후 저장, 응답 미포함."""

    client_id: str
    # asset_group·asset_type·status는 공통 코드 마스터(tb_code)로 관리 → 라우터에서 검증
    asset_group: str = Field(min_length=1, max_length=40)
    asset_type: Optional[str] = None  # ICE/EV/SOLAR/HEATPUMP 등
    quantity: Optional[int] = Field(default=None, ge=0)
    main_spec: Optional[str] = None
    telemetry_yn: str = Field(default="N", pattern="^[YN]$")
    location_info: Optional[str] = None
    status: str = Field(default="ACTIVE", min_length=1, max_length=40)
    agency_name: Optional[str] = None
    site_url: Optional[str] = None
    auth_type: str = Field(default="NONE", pattern="^(ID_PW|API_KEY|NONE)$")
    login_id: Optional[str] = None
    auth_value: Optional[str] = None  # ID_PW=비밀번호 / API_KEY=토큰 — 평문 저장 절대 금지
    usage_purpose: Optional[str] = None


class AssetUpdate(BaseModel):
    """자산 수정 — 전달된 필드만 반영. auth_value 전달 시 재암호화(빈 문자열은 삭제)."""

    client_id: Optional[str] = None
    asset_group: Optional[str] = Field(default=None, min_length=1, max_length=40)
    asset_type: Optional[str] = None
    quantity: Optional[int] = Field(default=None, ge=0)
    main_spec: Optional[str] = None
    telemetry_yn: Optional[str] = Field(default=None, pattern="^[YN]$")
    location_info: Optional[str] = None
    status: Optional[str] = Field(default=None, min_length=1, max_length=40)
    agency_name: Optional[str] = None
    site_url: Optional[str] = None
    auth_type: Optional[str] = Field(default=None, pattern="^(ID_PW|API_KEY|NONE)$")
    login_id: Optional[str] = None
    auth_value: Optional[str] = None
    usage_purpose: Optional[str] = None


class AssetListItem(AssetOut):
    """자산 목록 행 (SCR-04) — 고객사명 조인. 인증정보는 has_credentials·auth_type만."""

    client_name: Optional[str] = None


class AssetListResponse(BaseModel):
    items: List[AssetListItem]
    total: int


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


class ProjectCreate(BaseModel):
    client_id: Optional[str] = None  # 묶음 사업 시 대표사
    project_name: str = Field(min_length=1, max_length=200)
    reg_code: Optional[str] = None  # 예: R-2024-KR-03-000528
    # project_status는 공통 코드 마스터(PROJECT_STATUS)로 관리 → 라우터에서 검증
    project_status: str = Field(default="기획", min_length=1, max_length=40)
    reg_date: Optional[date] = None
    credit_start_date: Optional[date] = None
    credit_end_date: Optional[date] = None
    credit_period_type: Optional[str] = None
    mon_start_date: Optional[date] = None
    mon_end_date: Optional[date] = None
    mon_cycle: Optional[str] = None
    expected_issue_date: Optional[date] = None
    expected_credits: Optional[float] = Field(default=None, ge=0)
    unit_price: Optional[float] = Field(default=None, ge=0)  # §10.3 수기 단가
    issued_credits: Optional[float] = Field(default=None, ge=0)
    issued_at: Optional[date] = None
    manager_id: Optional[str] = None


class ProjectUpdate(BaseModel):
    client_id: Optional[str] = None
    project_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    reg_code: Optional[str] = None
    project_status: Optional[str] = Field(default=None, min_length=1, max_length=40)
    reg_date: Optional[date] = None
    credit_start_date: Optional[date] = None
    credit_end_date: Optional[date] = None
    credit_period_type: Optional[str] = None
    mon_start_date: Optional[date] = None
    mon_end_date: Optional[date] = None
    mon_cycle: Optional[str] = None
    expected_issue_date: Optional[date] = None
    expected_credits: Optional[float] = Field(default=None, ge=0)
    unit_price: Optional[float] = Field(default=None, ge=0)
    issued_credits: Optional[float] = Field(default=None, ge=0)
    issued_at: Optional[date] = None
    manager_id: Optional[str] = None


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
    unit_price: Optional[float] = None  # 🔒
    price_source: Optional[str] = None
    issued_credits: Optional[float] = None
    issued_at: Optional[date] = None
    manager_id: Optional[str] = None
    manager_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProjectListItem(ProjectOut):
    """목록 행 — 참여 고객사 수 포함."""

    client_count: int = 0


class ProjectListResponse(BaseModel):
    items: List[ProjectListItem]
    total: int


class UnitPriceUpdate(BaseModel):
    """배출권 단가 수기 입력 (§10.3) — null 전달 시 '미정'으로 초기화."""

    unit_price: Optional[float] = Field(default=None, ge=0)


class ProjectMapIn(BaseModel):
    """참여 고객사 매핑 등록/수정 — expected_amount는 서버 계산(§10.3)."""

    client_id: str
    asset_id: Optional[str] = None  # 연결 자산
    allocation_ratio: float = Field(ge=0, le=100)  # 배분율(%)
    success_fee_rate: float = Field(ge=0, le=100)  # 성공 보수율(%) 🔒


class ProjectMapOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    map_id: str
    project_id: str
    client_id: str
    client_name: Optional[str] = None
    asset_id: Optional[str] = None
    asset_summary: Optional[str] = None  # 연결 자산 요약 (분류·제원)
    allocation_ratio: Optional[float] = None
    success_fee_rate: Optional[float] = None  # 🔒
    expected_amount: Optional[float] = None  # 🔒 서버 계산 — 단가 미입력 시 null(미정)
    settlement_status: Optional[str] = None
    billed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    paid_amount: Optional[float] = None
    payment_type: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProjectDetailOut(ProjectOut):
    """사업 상세 (SCR-06) — 개요 + 참여 고객사 매핑 목록 + 배분율 합계."""

    clients: List[ProjectMapOut] = []
    allocation_total: float = 0  # 배분율 합계(100% 검증 UI용)


# ---------------------------------------------------------------------------
# P2 — 정산 (SCR-07)
# ---------------------------------------------------------------------------
class SettlementRow(BaseModel):
    """정산 행 — tb_project_client_map 기반. 금액은 항상 서버 계산 값."""

    map_id: str
    project_id: str
    project_name: Optional[str] = None
    client_id: str
    client_name: Optional[str] = None
    allocation_ratio: Optional[float] = None  # 지분율(%)
    success_fee_rate: Optional[float] = None  # 보수율(%) 🔒
    expected_amount: Optional[float] = None  # 예상 정산액 🔒 — 단가 미입력 시 null(미정)
    settlement_status: str
    unit_price: Optional[float] = None  # 🔒
    expected_credits: Optional[float] = None  # 🔒
    billed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    paid_amount: Optional[float] = None
    payment_type: Optional[str] = None


class SettlementListResponse(BaseModel):
    items: List[SettlementRow]
    total: int


class ClientProjectRow(BaseModel):
    """고객사 상세 '참여 사업·정산' 탭 행 (SCR-03D) — 매핑+사업 조인.

    보수율·예상 정산액 🔒은 프론트 SensitiveData 마스킹 대상(값은 그대로 응답).
    """

    map_id: str
    project_id: str
    project_name: Optional[str] = None
    project_status: Optional[str] = None  # 진행 상태 배지 (기획/등록완료/모니터링/검증/발급완료)
    allocation_ratio: Optional[float] = None  # 지분율(%)
    success_fee_rate: Optional[float] = None  # 보수율(%) 🔒
    expected_amount: Optional[float] = None  # 예상 정산액 🔒 — 단가 미입력 시 null(미정)
    settlement_status: str
    billed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class SettlementStatusUpdate(BaseModel):
    """정산 상태 전이 — STANDBY→BILLED→COMPLETED, 역행 금지(409). MANAGER 이상(§10.1)."""

    settlement_status: str = Field(pattern="^(STANDBY|BILLED|COMPLETED)$")
    paid_amount: Optional[float] = Field(default=None, ge=0)  # COMPLETED — 실입금액
    payment_type: Optional[str] = Field(default=None, pattern="^(FULL|PARTIAL)$")
    reason: Optional[str] = None  # 스냅샷 사유


# ---------------------------------------------------------------------------
# P1 — 활동 이력·이슈 (SCR-05 / 02)
# ---------------------------------------------------------------------------
class HistoryCreate(BaseModel):
    client_id: Optional[str] = None  # 미지정 고객 임시 이력 허용 (GAN E5)
    manager_id: Optional[str] = None  # 미지정 시 현재 사용자
    activity_date: datetime
    # activity_type은 공통 코드 마스터(ACTIVITY_TYPE)로 관리 → 라우터에서 검증
    activity_type: str = Field(min_length=1, max_length=40)
    retention_stage: Optional[str] = None
    # issue_status는 공통 코드 마스터(ISSUE_STATUS)로 관리 → 라우터에서 검증
    issue_status: Optional[str] = Field(default=None, min_length=1, max_length=40)
    priority: Optional[str] = Field(default=None, pattern="^(URGENT|NORMAL)$")
    due_date: Optional[date] = None
    next_action: Optional[str] = None
    title: str = Field(min_length=1, max_length=200)
    content: Optional[str] = None
    main_needs: Optional[str] = None


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

    issue_status: str = Field(min_length=1, max_length=40)
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
class ScheduleCreate(BaseModel):
    client_id: Optional[str] = None  # null = 내부 일정
    manager_id: Optional[str] = None  # 미지정 시 현재 사용자
    schedule_type: str = Field(pattern="^(MEETING|CALL|SITE_VISIT|REPORT_DUE|INTERNAL)$")
    title: str = Field(min_length=1, max_length=200)
    start_at: datetime
    end_at: Optional[datetime] = None
    location: Optional[str] = None
    memo: Optional[str] = None
    recur_rule: Optional[str] = None
    recur_until: Optional[date] = None


class ScheduleUpdate(BaseModel):
    """일자 드래그 변경·완료 처리 — DONE 전환 시 활동 이력 자동 적재."""

    client_id: Optional[str] = None
    manager_id: Optional[str] = None
    schedule_type: Optional[str] = Field(
        default=None, pattern="^(MEETING|CALL|SITE_VISIT|REPORT_DUE|INTERNAL)$"
    )
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    location: Optional[str] = None
    memo: Optional[str] = None
    status: Optional[str] = Field(default=None, pattern="^(PLANNED|DONE|CANCELED)$")
    result_note: Optional[str] = None  # 완료 시 조치 결과 — 자동 이력 content로 기록


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
    confirm_basis: Optional[str] = None  # CONFIRMED — 회신메일/유선/열람 (GAN B11)
    canceled_reason: Optional[str] = None  # CANCELED 시 필수 (R3-3)


class ReportSendRequest(BaseModel):
    reason: Optional[str] = None  # 정정 재발송 사유


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


class KakaoContactListResponse(BaseModel):
    items: List[KakaoContactOut]
    total: int


class KakaoContactUpdate(BaseModel):
    """연락처 승인 게이트 (CR-3) — APPROVED는 client_id 매핑 필수. MANAGER 이상."""

    status: str = Field(pattern="^(PENDING|APPROVED|REJECTED|BLOCKED)$")
    client_id: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    contact_role: Optional[str] = Field(default=None, pattern="^(REPRESENTATIVE|CONTACT)$")
    memo: Optional[str] = None


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


class ChatThreadUpdate(BaseModel):
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
    expected_billing_amount: Optional[float] = None  # 당월 예상 청구액 🔒 — 단가 미입력 시 None


class FunnelStage(BaseModel):
    stage: str
    count: int


class DashboardStats(BaseModel):
    period: str
    kpi: DashboardKpi
    funnel: List[FunnelStage]
    recent_activities: List[HistoryOut]
    open_issues: List[HistoryOut]


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
    code: str = Field(min_length=1, max_length=40, pattern="^[A-Za-z0-9_가-힣]+$")
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
    project_id: Optional[List[str]] = None
    asset_group: Optional[List[str]] = None
    settlement_status: Optional[List[str]] = None


def _parse_criteria_json(v):
    """DB Text(JSON 문자열) → dict — from_attributes 직렬화용. 파싱 실패 시 빈 조건."""
    if isinstance(v, str):
        try:
            parsed = json.loads(v) if v.strip() else {}
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            return {}
    return v if v is not None else {}


class SegmentIn(BaseModel):
    """세그먼트 생성 — criteria는 라우터에서 검증 후 JSON 문자열로 저장."""

    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=200)
    criteria: SegmentCriteria = Field(default_factory=SegmentCriteria)
    manager_id: Optional[str] = None
    # 세그먼트 기본 메일 템플릿 — null이면 발송 시 직접 입력/전역 기본
    mail_subject: Optional[str] = Field(default=None, max_length=200)
    mail_body: Optional[str] = None


class SegmentUpdate(BaseModel):
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
    """세그먼트 발송 요청 (B5) — doc_ids 1개 이상 필수(존재 검증은 라우터 404).

    subject/body 미지정 시 세그먼트 오버라이드 → tb_config report_mail_* → 코드 기본값.
    criteria는 즉석 발송(POST /segments/send)에서만 필수 — 저장 세그먼트 발송은 저장분 사용.
    """

    doc_ids: List[str] = Field(min_length=1)
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
