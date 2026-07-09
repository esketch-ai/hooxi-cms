"""Pydantic 스키마 — P0(auth·users·health) + P1(고객사·이력·일정·보고서·문서·대시보드)."""

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


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
