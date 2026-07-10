"""Pydantic 스키마 — P0(auth·users·health) + P1(고객사·이력·일정·보고서·문서·대시보드)
+ P2(자산·감축 사업·정산) + P3(카카오 채널·채팅 상담)."""

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
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# P1 — 고객사 (SCR-03 / 03D)
# ---------------------------------------------------------------------------
class ClientCreate(BaseModel):
    client_type: str = Field(pattern="^(TRANSPORT|FACILITY)$")
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
    contract_status: str = Field(default="ACTIVE", pattern="^(ACTIVE|HOLD|END)$")
    contract_date: Optional[datetime] = None
    keyman: Optional[str] = None
    manager_id: Optional[str] = None
    report_yn: str = Field(default="N", pattern="^[YN]$")
    lat: Optional[float] = None
    lng: Optional[float] = None
    subscription: Optional[ReportSubscriptionIn] = None  # 월간 보고서 설정


class ClientUpdate(BaseModel):
    client_type: Optional[str] = Field(default=None, pattern="^(TRANSPORT|FACILITY)$")
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
    contract_status: Optional[str] = Field(default=None, pattern="^(ACTIVE|HOLD|END)$")
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
    asset_group: str = Field(pattern="^(MOBILITY|FACILITY)$")
    asset_type: Optional[str] = None  # ICE/EV/SOLAR/HEATPUMP 등
    quantity: Optional[int] = Field(default=None, ge=0)
    main_spec: Optional[str] = None
    telemetry_yn: str = Field(default="N", pattern="^[YN]$")
    location_info: Optional[str] = None
    status: str = Field(default="ACTIVE", pattern="^(ACTIVE|INACTIVE|ERROR)$")
    agency_name: Optional[str] = None
    site_url: Optional[str] = None
    auth_type: str = Field(default="NONE", pattern="^(ID_PW|API_KEY|NONE)$")
    login_id: Optional[str] = None
    auth_value: Optional[str] = None  # ID_PW=비밀번호 / API_KEY=토큰 — 평문 저장 절대 금지
    usage_purpose: Optional[str] = None


class AssetUpdate(BaseModel):
    """자산 수정 — 전달된 필드만 반영. auth_value 전달 시 재암호화(빈 문자열은 삭제)."""

    client_id: Optional[str] = None
    asset_group: Optional[str] = Field(default=None, pattern="^(MOBILITY|FACILITY)$")
    asset_type: Optional[str] = None
    quantity: Optional[int] = Field(default=None, ge=0)
    main_spec: Optional[str] = None
    telemetry_yn: Optional[str] = Field(default=None, pattern="^[YN]$")
    location_info: Optional[str] = None
    status: Optional[str] = Field(default=None, pattern="^(ACTIVE|INACTIVE|ERROR)$")
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
    project_status: str = Field(default="기획", pattern=_PROJECT_STATUS_PATTERN)
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
    project_status: Optional[str] = Field(default=None, pattern=_PROJECT_STATUS_PATTERN)
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
    activity_type: str = Field(pattern="^(CALL|MEETING|SITE_VISIT|EMAIL|ISSUE|KAKAO)$")
    retention_stage: Optional[str] = None
    issue_status: Optional[str] = Field(default=None, pattern="^(OPEN|IN_PROGRESS|HOLD|CLOSED)$")
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

    issue_status: str = Field(pattern="^(OPEN|IN_PROGRESS|HOLD|CLOSED)$")
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
    """발송 현황 요약 바 — 대상 n개사 | 미착수·작성중·검토·발송완료·확인·취소."""

    target: int = 0
    standby: int = 0
    writing: int = 0
    review: int = 0
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
    status: str = Field(pattern="^(STANDBY|WRITING|REVIEW|SENT|CONFIRMED|CANCELED)$")
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
