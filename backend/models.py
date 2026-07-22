"""Hooxi-CMS 데이터 모델 — SCREEN_DESIGN_PLAN.md §6 (데이터 모델 v3.2) 전면 구현.

규약(PDF): 테이블명 tb_* / PK VARCHAR(50) (UUID 문자열) / 상태값 영문 대문자 /
created_at·updated_at 필수 / FK 명시.
"""

import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

# DATABASE_URL takes precedence (Cloud Run / docker-compose);
# otherwise assemble from individual DB_* variables (local .env)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://{user}:{password}@{host}:{port}/{name}".format(
        user=os.getenv("DB_USER", "hooxi"),
        password=os.getenv("DB_PASSWORD", "hooxi_secret"),
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        name=os.getenv("DB_NAME", "hooxi_cms"),
    ),
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def utcnow():
    # DB columns are TIMESTAMP WITHOUT TIME ZONE; store naive UTC
    return datetime.now(timezone.utc).replace(tzinfo=None)


def gen_uuid():
    # 규약: PK VARCHAR(50) — UUID 문자열 수용
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# 사용자 (CR-1: 네이버웍스 OAuth SSO — login_id/password_hash 폐지)
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "tb_user"

    user_id = Column(String(50), primary_key=True, default=gen_uuid)
    email = Column(String(100), unique=True, nullable=False, index=True)
    works_user_id = Column(String(100), index=True)  # 네이버웍스 사용자 ID(OAuth 매칭)
    auth_provider = Column(String(20), default="NAVER_WORKS")
    name = Column(String(50))
    position = Column(String(50))
    role = Column(String(20), nullable=False, default="STAFF")  # ADMIN/MANAGER/STAFF (§10.1)
    status = Column(String(20), nullable=False, default="PENDING")  # PENDING/ACTIVE/INACTIVE
    pin_hash = Column(String(255))  # 미팅 모드·reveal 게이트용 (R2-C11)
    token_version = Column(Integer, nullable=False, default=0)  # 즉시 무효화 (C2)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# ---------------------------------------------------------------------------
# PDF 정의 5테이블 (+ 플랜 §6.1 확장 필드)
# ---------------------------------------------------------------------------
class Client(Base):
    __tablename__ = "tb_client"

    client_id = Column(String(50), primary_key=True, default=gen_uuid)
    client_type = Column(String(20), nullable=False)  # TRANSPORT/FACILITY
    company_name = Column(String(100), nullable=False)
    biz_reg_no = Column(String(20))
    region = Column(String(20))
    address = Column(String(200))
    ceo_name = Column(String(50))
    ceo_contact_phone = Column(String(20))
    ceo_contact_email = Column(String(100))
    main_contact_name = Column(String(50))
    main_contact_phone = Column(String(20))  # 카카오톡 연동 시 매핑 기준
    main_contact_email = Column(String(100), index=True)  # AI 메일 발송 기준
    contract_status = Column(String(20), default="ACTIVE")  # ACTIVE/HOLD/END
    contract_date = Column(DateTime)
    keyman = Column(String(50))  # 주요 결정권자
    manager_id = Column(String(50), ForeignKey("tb_user.user_id"))  # 내부 담당 PM
    report_yn = Column(String(1), default="N")  # 보고서 대상 여부 (GAN A7)
    lat = Column(Numeric(10, 7))  # 지오코딩 — 결정 3호
    lng = Column(Numeric(10, 7))
    dropbox_folder = Column(String(255))  # provision된 Dropbox 전용 폴더 경로(없으면 미생성)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class Asset(Base):
    __tablename__ = "tb_asset"

    asset_id = Column(String(50), primary_key=True, default=gen_uuid)
    client_id = Column(String(50), ForeignKey("tb_client.client_id"), nullable=False)
    asset_group = Column(String(20), nullable=False)  # MOBILITY/FACILITY 등
    asset_type = Column(String(50))  # ICE/EV/SOLAR/HEATPUMP 등
    quantity = Column(Integer)
    main_spec = Column(String(100))
    telemetry_yn = Column(String(1), default="N")  # 관제 연동 여부
    location_info = Column(String(200))
    status = Column(String(20), default="ACTIVE")  # ACTIVE/INACTIVE/ERROR
    agency_name = Column(String(100))  # 대상 기관 (한국환경공단, 특정 FMS 관제사 등)
    site_url = Column(String(255))
    auth_type = Column(String(20))  # ID_PW/API_KEY/NONE
    login_id = Column(String(100))
    login_password = Column(String(255))  # 서버 AES-256 암호화 저장 (P2)
    api_token = Column(String(500))  # 암호화 저장 (P2)
    usage_purpose = Column(String(100))
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class ActivityHistory(Base):
    __tablename__ = "tb_activity_history"

    history_id = Column(String(50), primary_key=True, default=gen_uuid)
    # 미지정 고객 임시 이력 허용 — 미매핑 플래그 (GAN E5)
    client_id = Column(String(50), ForeignKey("tb_client.client_id"), nullable=True)
    manager_id = Column(String(50), ForeignKey("tb_user.user_id"), nullable=False)  # 재지정 가능 담당자
    created_by = Column(String(50), ForeignKey("tb_user.user_id"))  # 불변 작성자 (GAN A1)
    activity_date = Column(DateTime, nullable=False)
    activity_type = Column(String(20), nullable=False)  # CALL/MEETING/SITE_VISIT/EMAIL/ISSUE/KAKAO
    retention_stage = Column(String(20))  # 인지~확장 8단계
    issue_status = Column(String(20))  # OPEN/IN_PROGRESS/HOLD/CLOSED (ISSUE 전용)
    priority = Column(String(10))  # URGENT/NORMAL (ISSUE 전용 — 결정 1호)
    due_date = Column(Date)  # 이슈 마감일 (GAN A2)
    next_action = Column(String(200))  # GAN A3
    next_action_done = Column(String(1), default="N")
    related_history_id = Column(
        String(50), ForeignKey("tb_activity_history.history_id"), nullable=True
    )  # 이슈 승격 원 이력 링크 (R2-D6)
    title = Column(String(200), nullable=False)
    content = Column(Text)
    main_needs = Column(String(200))
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class Project(Base):
    __tablename__ = "tb_project"

    project_id = Column(String(50), primary_key=True, default=gen_uuid)
    client_id = Column(String(50), ForeignKey("tb_client.client_id"))  # 묶음 사업 시 대표사
    project_name = Column(String(200), nullable=False)
    reg_code = Column(String(50))  # 예: R-2020-KR-03-000528
    project_status = Column(String(20), nullable=False)  # 기획/등록완료/모니터링/검증/발급완료
    reg_date = Column(Date)
    credit_start_date = Column(Date)
    credit_end_date = Column(Date)
    credit_period_type = Column(String(20))
    mon_start_date = Column(Date)
    mon_end_date = Column(Date)
    mon_cycle = Column(String(50))
    expected_issue_date = Column(Date)
    expected_credits = Column(Numeric(10, 2))
    unit_price = Column(Numeric(15, 2))  # 수기 단가 (§10.3)
    price_source = Column(String(20), default="MANUAL")  # MANUAL → MARKET 확장
    issued_credits = Column(Numeric(10, 2))  # 확정 발급량 — 발급완료 전환 시 필수 (R2-A1)
    issued_at = Column(Date)
    manager_id = Column(String(50), ForeignKey("tb_user.user_id"))
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class ProjectClientMap(Base):
    __tablename__ = "tb_project_client_map"

    map_id = Column(String(50), primary_key=True, default=gen_uuid)
    project_id = Column(String(50), ForeignKey("tb_project.project_id"), nullable=False)
    client_id = Column(String(50), ForeignKey("tb_client.client_id"), nullable=False)
    # 같은 (사업, 고객사) 매핑 중복 방지 — 동시 등록 경합 백스톱 (앱 검사 + DB 제약)
    __table_args__ = (
        UniqueConstraint("project_id", "client_id", name="uq_project_client_map_slot"),
    )
    asset_id = Column(String(50), ForeignKey("tb_asset.asset_id"), nullable=True)
    allocation_ratio = Column(Numeric(5, 2))  # 배출권 배분 비율(%)
    success_fee_rate = Column(Numeric(5, 2))  # 성공 보수율(%)
    expected_amount = Column(Numeric(15, 2))  # 서버 계산 (§10.3)
    settlement_status = Column(String(20), default="STANDBY")  # STANDBY/BILLED/COMPLETED
    # 청구 증빙 (GAN A5) — 최신 상태만 보유, 회차 스냅샷은 tb_settlement_snapshot (R3-1)
    billed_at = Column(DateTime)
    billed_by = Column(String(50), ForeignKey("tb_user.user_id"))
    completed_at = Column(DateTime)
    completed_by = Column(String(50), ForeignKey("tb_user.user_id"))
    paid_amount = Column(Numeric(15, 2))
    payment_type = Column(String(20))  # FULL/PARTIAL
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# ---------------------------------------------------------------------------
# 신규 테이블 (플랜 §6.2)
# ---------------------------------------------------------------------------
class Schedule(Base):
    __tablename__ = "tb_schedule"

    schedule_id = Column(String(50), primary_key=True, default=gen_uuid)
    client_id = Column(String(50), ForeignKey("tb_client.client_id"), nullable=True)  # 내부 일정
    manager_id = Column(String(50), ForeignKey("tb_user.user_id"), nullable=False)
    schedule_type = Column(String(20), nullable=False)  # MEETING/CALL/SITE_VISIT/REPORT_DUE/INTERNAL
    title = Column(String(200), nullable=False)
    start_at = Column(DateTime, nullable=False)
    end_at = Column(DateTime)
    location = Column(String(200))  # 현장 주소, 내비 딥링크 원천 (GAN A8)
    memo = Column(Text)
    status = Column(String(20), default="PLANNED")  # PLANNED/DONE/CANCELED (R2-D9)
    recur_rule = Column(String(50))  # 예: MONTHLY
    recur_until = Column(Date)  # 반복 종료일 (R3-9)
    parent_schedule_id = Column(
        String(50), ForeignKey("tb_schedule.schedule_id"), nullable=True
    )  # 반복 템플릿의 회차 실체화 (R2-D8)
    history_id = Column(
        String(50), ForeignKey("tb_activity_history.history_id"), nullable=True
    )  # 완료 시 생성된 활동 이력 연결
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class ReportDelivery(Base):
    __tablename__ = "tb_report_delivery"
    __table_args__ = (
        UniqueConstraint("client_id", "period", "report_type", name="uq_report_delivery_slot"),
    )

    report_id = Column(String(50), primary_key=True, default=gen_uuid)
    client_id = Column(String(50), ForeignKey("tb_client.client_id"), nullable=False)
    period = Column(String(7), nullable=False)  # 'YYYY-MM'
    report_type = Column(String(50), nullable=False)
    # STANDBY/WRITING/REVIEW/SENT/CONFIRMED/CANCELED(GAN A13)/MERGED(R3-5)
    status = Column(String(20), nullable=False, default="STANDBY")
    canceled_reason = Column(String(200))  # 취소·복원 사유 (R3-3)
    due_date = Column(Date)
    sent_at = Column(DateTime)  # 최종 발송 요약 — 회차별 상세는 send_log
    sent_channel = Column(String(20))  # EMAIL/KAKAO/BOTH
    confirmed_at = Column(DateTime)
    confirm_basis = Column(String(20))  # 회신메일/유선/열람 (GAN B11)
    doc_id = Column(
        String(50), ForeignKey("tb_document.doc_id", use_alter=True, name="fk_report_doc"),
        nullable=True,
    )  # 최신 표시용
    pinned_doc_id = Column(
        String(50), ForeignKey("tb_document.doc_id", use_alter=True, name="fk_report_pinned_doc"),
        nullable=True,
    )  # 발송 후보 고정 (R2-B4)
    reviewed_by = Column(String(50), ForeignKey("tb_user.user_id"), nullable=True)  # R2-B10
    reviewed_at = Column(DateTime)
    manager_id = Column(String(50), ForeignKey("tb_user.user_id"))
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class ReportSendLog(Base):
    """발송 이력 — GAN A6, append-only (result만 배달 이벤트로 사후 갱신 허용, R3-4)."""

    __tablename__ = "tb_report_send_log"

    send_id = Column(String(50), primary_key=True, default=gen_uuid)
    report_id = Column(String(50), ForeignKey("tb_report_delivery.report_id"), nullable=False)
    seq = Column(Integer, nullable=False)  # 모든 발송 시도는 무조건 새 seq (R2-B3)
    sent_doc_id = Column(String(50), ForeignKey("tb_document.doc_id"))  # 발송 시점 파일 버전 고정
    recipients = Column(Text)  # 수신자 스냅샷
    channel = Column(String(20))  # 채널당 1행(동일 seq 공유) — R2-B2
    result = Column(String(20))  # SUCCESS/FAIL/BOUNCED(P2)
    result_updated_at = Column(DateTime)  # SUCCESS→BOUNCED 사후 갱신 (R3-4)
    confirmed_at = Column(DateTime)  # 회차별 고객확인 보존 (R3-6)
    confirm_basis = Column(String(20))
    confirmed_by = Column(String(50), ForeignKey("tb_user.user_id"), nullable=True)
    sent_by = Column(String(50), ForeignKey("tb_user.user_id"))  # 대리 발송자 포함
    reason = Column(String(200))  # 정정 재발송 사유
    created_at = Column(DateTime, default=utcnow)


class ReportSubscription(Base):
    __tablename__ = "tb_report_subscription"
    __table_args__ = (
        UniqueConstraint("client_id", "report_type", name="uq_report_subscription_slot"),
    )

    sub_id = Column(String(50), primary_key=True, default=gen_uuid)
    client_id = Column(String(50), ForeignKey("tb_client.client_id"), nullable=False)
    report_type = Column(String(50), nullable=False)
    channel = Column(String(20), default="EMAIL")  # EMAIL/KAKAO/BOTH
    due_day = Column(Integer)  # 1~31, 짧은 달은 말일 보정
    active = Column(String(1), default="Y")
    mail_subject = Column(String(200))  # 고객사별 메일 제목 템플릿 오버라이드 (null=전역 기본)
    mail_body = Column(Text)  # 고객사별 메일 본문 템플릿 오버라이드 (null=전역 기본)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class ReportRecipient(Base):
    __tablename__ = "tb_report_recipient"

    recipient_id = Column(String(50), primary_key=True, default=gen_uuid)
    client_id = Column(String(50), ForeignKey("tb_client.client_id"), nullable=False)
    name = Column(String(50))
    email = Column(String(100), nullable=False)
    cc_yn = Column(String(1), default="N")  # TO(cc_yn=N) 최소 1명 검증은 서비스 계층 (R2-B5)
    sub_id = Column(
        String(50), ForeignKey("tb_report_subscription.sub_id"), nullable=True
    )  # null=전 유형 공통 (R2-B8)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class Document(Base):
    __tablename__ = "tb_document"
    __table_args__ = (
        # 보고서 버전 max+1 동시 계산 경합 시 중복 방지 (P0-B) — report_id NULL(비보고서
        # 문서 다수)은 SQLite/PG 모두 유니크 충돌 대상이 아니므로 안전.
        UniqueConstraint("report_id", "version", name="uq_document_report_version"),
    )

    doc_id = Column(String(50), primary_key=True, default=gen_uuid)
    client_id = Column(
        String(50), ForeignKey("tb_client.client_id"), nullable=True
    )  # 공용 양식·미지정 이력 사진 (R2-C6)
    doc_type = Column(String(20), nullable=False)  # CONTRACT/REPORT/FORM/PHOTO/ETC
    title = Column(String(200), nullable=False)
    file_url = Column(String(255), nullable=False)
    version = Column(Integer, default=1)
    report_id = Column(String(50), ForeignKey("tb_report_delivery.report_id"), nullable=True)
    history_id = Column(
        String(50), ForeignKey("tb_activity_history.history_id"), nullable=True
    )  # 활동 이력·이슈 첨부 (R2-C6)
    asset_id = Column(
        String(50), ForeignKey("tb_asset.asset_id"), nullable=True
    )  # 자산별 사진(제원표 등) 역조회
    uploaded_by = Column(String(50), ForeignKey("tb_user.user_id"))
    created_at = Column(DateTime, default=utcnow)


class IssueComment(Base):
    __tablename__ = "tb_issue_comment"

    comment_id = Column(String(50), primary_key=True, default=gen_uuid)
    history_id = Column(String(50), ForeignKey("tb_activity_history.history_id"), nullable=False)
    manager_id = Column(String(50), ForeignKey("tb_user.user_id"), nullable=False)
    comment_type = Column(String(20), default="COMMENT")  # COMMENT/STATUS_CHANGE/ASSIGN (GAN A4)
    content = Column(Text)
    created_at = Column(DateTime, default=utcnow)


class Config(Base):
    __tablename__ = "tb_config"

    config_key = Column(String(50), primary_key=True)
    config_value = Column(Text)
    description = Column(String(200))
    updated_by = Column(String(50), ForeignKey("tb_user.user_id"))
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class ConfigHistory(Base):
    __tablename__ = "tb_config_history"

    history_id = Column(String(50), primary_key=True, default=gen_uuid)
    config_key = Column(String(50), ForeignKey("tb_config.config_key"), nullable=False)
    old_value = Column(Text)
    new_value = Column(Text)
    updated_by = Column(String(50), ForeignKey("tb_user.user_id"))
    created_at = Column(DateTime, default=utcnow)


class Code(Base):
    """공통 코드 마스터 — 화면에서 추가·수정·비활성 가능한 분류값 (예: 고객사 구분).

    - code: DB에 저장되는 불변 코드값(예: TRANSPORT). 생성 후 변경 불가.
    - label: 화면 표시명(예: 운수사). 언제든 수정 가능(기존 데이터 안 깨짐).
    - active: 'N'이면 신규 선택지에서 숨김(기존 데이터는 유지·표시).
    - is_system: 'Y'는 내장 코드 — 삭제 불가(비활성만 가능).
    """

    __tablename__ = "tb_code"
    __table_args__ = (UniqueConstraint("category", "code", name="uq_code_category_code"),)

    code_id = Column(String(50), primary_key=True, default=gen_uuid)
    category = Column(String(40), nullable=False, index=True)  # CLIENT_TYPE 등
    code = Column(String(40), nullable=False)  # TRANSPORT (불변)
    label = Column(String(100), nullable=False)  # 운수사 (수정 가능)
    color = Column(String(20))  # 상태 배지·지도·칸반 색상(시맨틱 팔레트명, 예: emerald)
    extra = Column(String(255))  # 카테고리별 부가값 — AGENCY는 기본 접속 URL
    sort_order = Column(Integer, default=0)
    active = Column(String(1), nullable=False, default="Y")  # Y/N
    is_system = Column(String(1), nullable=False, default="N")  # 내장 코드 보호
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class AuditLog(Base):
    """감사 로그 — GAN A10. 비밀번호·해시·인증정보 값 기록 절대 금지 (R2-E6)."""

    __tablename__ = "tb_audit_log"

    log_id = Column(String(50), primary_key=True, default=gen_uuid)
    actor_id = Column(String(50), ForeignKey("tb_user.user_id"), nullable=False)
    # REVEAL_AUTH/DOWNLOAD/ACCOUNT_CHANGE/CLIENT_KEY_CHANGE/PRIVACY_OFF
    # + HANDOVER/MERGE/SETTLEMENT_CHANGE/AUDIT_VIEW (R2) + KAKAO_APPROVAL (CR-3)
    action = Column(String(30), nullable=False)
    target_type = Column(String(30))
    target_id = Column(String(50))
    old_value = Column(Text)
    new_value = Column(Text)
    created_at = Column(DateTime, default=utcnow)


class KpiSnapshot(Base):
    __tablename__ = "tb_kpi_snapshot"

    snapshot_id = Column(String(50), primary_key=True, default=gen_uuid)
    period = Column(String(7), nullable=False)  # 'YYYY-MM' — 기준 시각 말일 23:59 (R2-E8)
    metrics = Column(Text)  # JSON: 고객사 수·상태별 이슈·보고서 발송률·예상 청구액·당월 실입금 합
    created_at = Column(DateTime, default=utcnow)


class SettlementSnapshot(Base):
    """정산 증빙 회차 — R3-1. 불변(append-only), map에는 최신 상태만."""

    __tablename__ = "tb_settlement_snapshot"
    __table_args__ = (
        # 회차 seq max+1 동시 계산 경합 시 중복 방지 (P0-B 준용) — 같은 map의
        # 동일 회차 이중 동결 차단
        UniqueConstraint("map_id", "seq", name="uq_settlement_snapshot_map_seq"),
    )

    snapshot_id = Column(String(50), primary_key=True, default=gen_uuid)
    map_id = Column(String(50), ForeignKey("tb_project_client_map.map_id"), nullable=False)
    seq = Column(Integer, nullable=False)
    # 5요소 동결
    issued_credits = Column(Numeric(10, 2))
    amount = Column(Numeric(15, 2))
    unit_price = Column(Numeric(15, 2))
    allocation_ratio = Column(Numeric(5, 2))
    success_fee_rate = Column(Numeric(5, 2))
    paid_amount = Column(Numeric(15, 2))
    action = Column(String(20), nullable=False)  # BILLED/REBILLED/REVERTED/COMPLETED
    reason = Column(String(200))
    created_by = Column(String(50), ForeignKey("tb_user.user_id"))
    created_at = Column(DateTime, default=utcnow)


class KakaoContact(Base):
    """카카오 고객 연락처 승인 — CR-3. 승인 전 AI는 일반 안내만(보안 게이트)."""

    __tablename__ = "tb_kakao_contact"

    contact_id = Column(String(50), primary_key=True, default=gen_uuid)
    kakao_user_key = Column(String(100), unique=True, nullable=False)
    client_id = Column(String(50), ForeignKey("tb_client.client_id"), nullable=True)  # 승인 시 확정
    name = Column(String(50))
    phone = Column(String(20))
    contact_role = Column(String(20))  # REPRESENTATIVE/CONTACT
    status = Column(String(20), default="PENDING")  # PENDING/APPROVED/REJECTED/BLOCKED
    requested_at = Column(DateTime, default=utcnow)
    approved_by = Column(String(50), ForeignKey("tb_user.user_id"), nullable=True)
    approved_at = Column(DateTime)
    memo = Column(String(200))
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class ChatThread(Base):
    __tablename__ = "tb_chat_thread"

    thread_id = Column(String(50), primary_key=True, default=gen_uuid)
    client_id = Column(
        String(50), ForeignKey("tb_client.client_id"), nullable=True
    )  # kakao_contact 승인 시 확정 (CR-3)
    kakao_contact_id = Column(String(50), ForeignKey("tb_kakao_contact.contact_id"))
    mode = Column(String(20), default="AI")  # AI/HUMAN
    status = Column(String(20), default="OPEN")  # OPEN/WAITING/CLOSED
    last_message_at = Column(DateTime)
    assigned_manager_id = Column(String(50), ForeignKey("tb_user.user_id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class ChatMessage(Base):
    __tablename__ = "tb_chat_message"

    message_id = Column(String(50), primary_key=True, default=gen_uuid)
    thread_id = Column(String(50), ForeignKey("tb_chat_thread.thread_id"), nullable=False)
    sender_type = Column(String(20), nullable=False)  # CUSTOMER/AI/STAFF/SYSTEM
    sender_id = Column(String(50), ForeignKey("tb_user.user_id"), nullable=True)
    content = Column(Text)
    created_at = Column(DateTime, default=utcnow)


# ---------------------------------------------------------------------------
# 세그먼트 보고서 발송 (SCR-12 확장) — 조건 기반 고객사 묶음 + 1회성 발송 이력
# ---------------------------------------------------------------------------
class Segment(Base):
    """저장된 세그먼트 — criteria는 JSON 문자열(축 간 AND, 축 내 IN/OR).

    삭제는 soft(active=N) — tb_segment_send.segment_id 발송 이력 참조 보존.
    """

    __tablename__ = "tb_segment"

    segment_id = Column(String(50), primary_key=True, default=gen_uuid)
    name = Column(String(100), nullable=False)
    description = Column(String(200))
    criteria = Column(Text)  # JSON: {region:[..], client_type:[..], ...}
    active = Column(String(1), default="Y")  # N=soft 삭제(신규 선택지에서 숨김)
    manager_id = Column(String(50), ForeignKey("tb_user.user_id"))
    mail_subject = Column(String(200))  # 세그먼트 기본 메일 제목 템플릿 (null=전역 기본)
    mail_body = Column(Text)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class SegmentSend(Base):
    """세그먼트 발송 실행 이력 — 실행 시점 조건·문서·본문 스냅샷 (append-only)."""

    __tablename__ = "tb_segment_send"

    send_id = Column(String(50), primary_key=True, default=gen_uuid)
    segment_id = Column(
        String(50), ForeignKey("tb_segment.segment_id"), nullable=True
    )  # null=저장 없이 즉석 발송
    criteria_snapshot = Column(Text)  # 발송 시점 조건 JSON 동결
    doc_ids = Column(Text)  # JSON 배열 — 첨부 문서 doc_id 목록
    subject = Column(String(200))  # 발송 제목 스냅샷
    body = Column(Text)  # 발송 본문 스냅샷
    target_count = Column(Integer, default=0)
    sent_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    sent_by = Column(String(50), ForeignKey("tb_user.user_id"))
    created_at = Column(DateTime, default=utcnow)


class SegmentSendLog(Base):
    """세그먼트 발송 고객사별 결과 — append-only (수신자 스냅샷 포함)."""

    __tablename__ = "tb_segment_send_log"

    log_id = Column(String(50), primary_key=True, default=gen_uuid)
    send_id = Column(String(50), ForeignKey("tb_segment_send.send_id"), nullable=False)
    client_id = Column(String(50), ForeignKey("tb_client.client_id"), nullable=False)
    recipients = Column(Text)  # 수신자 스냅샷 JSON
    channel = Column(String(10), default="EMAIL")
    result = Column(String(10))  # SUCCESS/FAIL
    reason = Column(String(300))  # 실패 사유
    created_at = Column(DateTime, default=utcnow)


def ensure_schema():
    """create_all은 '없는 테이블'만 만들고 '기존 테이블의 신규 컬럼'은 추가하지 않는다.
    Alembic 미도입 상태에서 배포된 테이블에 누락된 컬럼을 idempotent하게 보강한다.

    (배포 tb_code에 color 컬럼 누락 → 조회 SELECT 500 사례 대응. PostgreSQL·SQLite 공통
    ALTER TABLE ADD COLUMN 사용, inspector로 존재 여부 확인해 IF NOT EXISTS 방언차 회피.)
    """
    from sqlalchemy import inspect as _inspect, text as _text

    # (table, column, DDL 타입) — 배포 이후 모델에 추가된 컬럼
    required = [
        ("tb_code", "color", "VARCHAR(20)"),
        ("tb_code", "extra", "VARCHAR(255)"),
        ("tb_document", "asset_id", "VARCHAR(50)"),
        ("tb_report_subscription", "mail_subject", "VARCHAR(200)"),
        ("tb_report_subscription", "mail_body", "TEXT"),
        ("tb_client", "dropbox_folder", "VARCHAR(255)"),
    ]
    try:
        insp = _inspect(engine)
        tables = set(insp.get_table_names())
        for table, column, ddl in required:
            if table not in tables:
                continue
            cols = {c["name"] for c in insp.get_columns(table)}
            if column not in cols:
                with engine.begin() as conn:
                    conn.execute(_text("ALTER TABLE {0} ADD COLUMN {1} {2}".format(table, column, ddl)))
                print("✓ Added missing column {0}.{1}".format(table, column))
    except Exception as exc:
        print("⚠ ensure_schema skipped: {0}".format(exc))

    # 배포된 테이블에 유니크 인덱스 보강 (P0-B) — create_all은 기존 테이블에 제약을
    # 추가하지 않음. 신규 DB는 __table_args__의 UniqueConstraint로 생성되므로 동일
    # 컬럼 유니크가 이미 있으면 건너뛴다 (SQLite/PostgreSQL 공통 표준 구문).
    # (index_name, table, 컬럼 목록) — NULL 다수 컬럼이어도 유니크 충돌 없음
    unique_indexes = [
        # 보고서 버전 max+1 동시 계산 경합 방지 (P0-B)
        ("uq_document_report_version", "tb_document", ["report_id", "version"]),
        # 정산 회차 seq max+1 동시 계산 경합 방지 (P0-B 준용, R3-1)
        ("uq_settlement_snapshot_map_seq", "tb_settlement_snapshot", ["map_id", "seq"]),
        # 같은 (사업, 고객사) 매핑 중복 방지 — 이중 청구 예방 (DB 정밀검사 F2)
        ("uq_project_client_map_slot", "tb_project_client_map", ["project_id", "client_id"]),
    ]
    try:
        insp = _inspect(engine)
        tables = set(insp.get_table_names())
        for index_name, table, columns in unique_indexes:
            if table not in tables:
                continue
            target_cols = set(columns)
            has_unique = any(
                set(uc.get("column_names") or []) == target_cols
                for uc in insp.get_unique_constraints(table)
            ) or any(
                ix.get("unique") and set(ix.get("column_names") or []) == target_cols
                for ix in insp.get_indexes(table)
            )
            if not has_unique:
                with engine.begin() as conn:
                    conn.execute(
                        _text(
                            "CREATE UNIQUE INDEX IF NOT EXISTS {0} "
                            "ON {1} ({2})".format(index_name, table, ", ".join(columns))
                        )
                    )
                print("✓ Added unique index {0}".format(index_name))
    except Exception as exc:
        print("⚠ ensure_schema unique index skipped: {0}".format(exc))

    # 조회 성능 인덱스 보강 (DB 정밀검사 F5) — 성장 대비 1~4순위.
    # CREATE INDEX IF NOT EXISTS는 SQLite/PostgreSQL 공통이라 신규·기존 DB 동일 적용.
    plain_indexes = [
        # 1) 활동 이력 — 최대 성장 테이블: 날짜 정렬·고객 타임라인·담당·이슈 보드 필터
        ("ix_history_activity_date", "tb_activity_history", ["activity_date"]),
        ("ix_history_client", "tb_activity_history", ["client_id"]),
        ("ix_history_manager", "tb_activity_history", ["manager_id"]),
        ("ix_history_type_status", "tb_activity_history", ["activity_type", "issue_status"]),
        # 2) 채팅 메시지 — 스레드별 로드 + 5초 폴링
        ("ix_chat_message_thread_created", "tb_chat_message", ["thread_id", "created_at"]),
        # 3) 감사 로그 — append-only 무한 성장, 최신순·행위자 필터
        ("ix_audit_created", "tb_audit_log", ["created_at"]),
        ("ix_audit_actor", "tb_audit_log", ["actor_id"]),
        # 4) 보고서 — 월별 목록·배치의 period+status 스캔
        ("ix_report_period_status", "tb_report_delivery", ["period", "status"]),
    ]
    try:
        insp = _inspect(engine)
        tables = set(insp.get_table_names())
        for index_name, table, columns in plain_indexes:
            if table not in tables:
                continue
            existing = {ix.get("name") for ix in insp.get_indexes(table)}
            if index_name not in existing:
                with engine.begin() as conn:
                    conn.execute(
                        _text(
                            "CREATE INDEX IF NOT EXISTS {0} ON {1} ({2})".format(
                                index_name, table, ", ".join(columns)
                            )
                        )
                    )
                print("✓ Added index {0}".format(index_name))
    except Exception as exc:
        print("⚠ ensure_schema plain index skipped: {0}".format(exc))


def init_db():
    """Create tables if the database is reachable. Called at app startup —
    must not raise, or Cloud Run will crash-loop when the DB is unset."""
    try:
        Base.metadata.create_all(bind=engine)
        ensure_schema()  # 기존 테이블 누락 컬럼 보강 (create_all 한계 보완)
        print("✓ Database tables ready")
        return True
    except Exception as exc:
        print(f"⚠ Database unavailable, starting without it: {exc}")
        return False
