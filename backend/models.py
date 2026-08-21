"""Hooxi-CMS 데이터 모델 — SCREEN_DESIGN_PLAN.md §6 (데이터 모델 v3.2) 전면 구현.

규약(PDF): 테이블명 tb_* / PK VARCHAR(50) (UUID 문자열) / 상태값 영문 대문자 /
created_at·updated_at 필수 / FK 명시.
"""

import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
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
    # 이메일 유니크 해제 — 같은 사람(대표·임원)이 여러 고객사·투자사 외부 포털 계정을 가질 수
    # 있고, 내부 계정과 같은 이메일의 외부 계정도 허용한다. 로그인 경로는 전부 스코프 조회
    # (내부 JIT/dev-login=내부 역할만, 포털=user_id 토큰)라 이메일 중복이 안전하다.
    email = Column(String(100), nullable=False, index=True)
    works_user_id = Column(String(100), index=True)  # 네이버웍스 사용자 ID(OAuth 매칭)
    auth_provider = Column(String(20), default="NAVER_WORKS")
    name = Column(String(50))
    position = Column(String(50))
    role = Column(String(20), nullable=False, default="STAFF")  # 내부 ADMIN/MANAGER/STAFF (§10.1) / 외부 PARTNER·INVESTOR(부록 N.8 D3, 격리)
    status = Column(String(20), nullable=False, default="PENDING")  # PENDING/ACTIVE/INACTIVE
    # 외부역할 연결(nullable) — PARTNER=운수사 계정, INVESTOR=매수자 계정 (온보딩 INC-6에서 세팅)
    # tb_client.manager_id → tb_user 와 순환 FK가 되므로 use_alter로 사이클을 명시(생성/삭제 정렬 경고 회피).
    client_id = Column(
        String(50),
        ForeignKey("tb_client.client_id", ondelete="SET NULL", use_alter=True, name="fk_user_client"),
    )
    buyer_id = Column(String(50), ForeignKey("tb_buyer.buyer_id", ondelete="SET NULL"))
    phone = Column(String(20))  # 외부 포털 매직링크 알림톡 발송 대상(INC-9) — 없으면 발송 스킵
    # 외부 포털 이용권 만료(1일/1주/1개월/연간권) — 내부 계정은 항상 NULL(무관).
    # 만료 후 포털 인증(매직링크 verify·access 재검증)이 401로 차단된다.
    portal_expires_at = Column(DateTime)
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
    # 운수사 명부(민원대응 회원명부) 추가 정보 — 팩스·면허일자·버스 대수(시내/농어촌/시외, 변경 잦음)
    fax = Column(String(20))
    corp_reg_no = Column(String(20))  # 법인등록번호(운수사 정보)
    license_date = Column(Date)  # 면허일자
    bus_city = Column(Integer)  # 시내버스 대수
    bus_rural = Column(Integer)  # 농어촌버스 대수
    bus_intercity = Column(Integer)  # 시외버스 대수
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
    max_payment = Column(Numeric(15, 2))  # 최대지급액(차량당 상한) — expected_payout 파생 기준(부록 L)
    base_reduction = Column(Numeric(10, 3))  # 기준감축량(기본 240)
    base_vehicle_age = Column(Numeric(5, 2))  # 기준차령(기본 8)
    approved_at = Column(Date)  # 승인일(승인=NOT NULL). 지급 파라미터 입력 시 자동 세팅
    approval_status = Column(String(20))  # APPROVAL_STATUS: 미승인/승인 — 미착품 전환 스위치(부록 L)
    issued_credits = Column(Numeric(10, 2))  # 확정 발급량 — 발급완료 전환 시 필수 (R2-A1)
    issued_at = Column(Date)
    manager_id = Column(String(50), ForeignKey("tb_user.user_id"))
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class ProjectStage(Base):
    """사업 진행 단계 타임라인 — Phase 1(단계·지연 관찰). 프로젝트당 PROJECT_STATUS
    코드별 1행. 예정일/실제일을 두고, 예정 경과 & 미도달(실제일 없음)이면 지연으로 판정.
    (경량 모델 — 마일스톤 다건 아님. stage_code는 공통코드 PROJECT_STATUS 재사용)"""

    __tablename__ = "tb_project_stage"

    stage_id = Column(String(50), primary_key=True, default=gen_uuid)
    project_id = Column(
        String(50),
        ForeignKey("tb_project.project_id", ondelete="CASCADE"),
        nullable=False,
    )
    stage_code = Column(String(20), nullable=False)  # PROJECT_STATUS 코드값(한글)
    planned_date = Column(Date)  # 예정일(수기)
    actual_date = Column(Date)  # 실제 도달일(상태 전이 시 자동 or 수기 소급)
    sort_order = Column(Integer)  # 단계 순서(공통코드 sort_order 승계)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    __table_args__ = (
        UniqueConstraint("project_id", "stage_code", name="uq_project_stage_slot"),
    )


class ProjectVehicle(Base):
    """사업 참여 차량 — Phase 2 원가/지급 축의 감축량·예상지급액 기반(부록 F.2/G).

    감축량 방법론(신규/대체, 부록 G)은 전문 스프레드시트가 산정하고, CMS는 그 결과인
    연차(1~10) 감축량·도입구분·민간투자비율을 ingest한다(Option A). total_reduction은 서버 파생.
    expected_payout(운수사 예상지급액)은 순수 파생값(부록 L 정본 산식) — 수기 입력 없음.
    차령만료일·잔여차령·잔여반영감축량도 서버 파생값(부록 L).
    """

    __tablename__ = "tb_project_vehicle"

    vehicle_id = Column(String(50), primary_key=True, default=gen_uuid)
    project_id = Column(
        String(50),
        ForeignKey("tb_project.project_id", ondelete="CASCADE"),
        nullable=False,
    )
    client_id = Column(
        String(50), ForeignKey("tb_client.client_id", ondelete="SET NULL")
    )  # 운수사
    asset_id = Column(
        String(50), ForeignKey("tb_asset.asset_id", ondelete="SET NULL")
    )  # 선택적 자산 연결
    vehicle_no = Column(String(30))  # 차량번호
    region = Column(String(20))
    introduction_type = Column(String(20))  # 공통코드 VEHICLE_INTRO: 신규도입/대체도입
    registered_at = Column(Date)  # 차량등록일
    # 연차(1~10차) 감축량 — 방법론 산정 결과 ingest
    reduction_y1 = Column(Numeric(12, 3))
    reduction_y2 = Column(Numeric(12, 3))
    reduction_y3 = Column(Numeric(12, 3))
    reduction_y4 = Column(Numeric(12, 3))
    reduction_y5 = Column(Numeric(12, 3))
    reduction_y6 = Column(Numeric(12, 3))
    reduction_y7 = Column(Numeric(12, 3))
    reduction_y8 = Column(Numeric(12, 3))
    reduction_y9 = Column(Numeric(12, 3))
    reduction_y10 = Column(Numeric(12, 3))
    total_reduction = Column(Numeric(14, 3))  # 파생: 연차 단순합(서버 계산·저장)
    private_invest_ratio = Column(Numeric(5, 2))  # 민간투자비율(%)
    expire_at = Column(Date)  # 파생: 차령만료일(EDATE(등록일,108)-1, 부록 L)
    remaining_age = Column(Numeric(6, 3))  # 파생: 잔여차령(CLAMP(0,기준차령,(만료-승인)/365), 부록 L)
    effective_reduction = Column(Numeric(14, 3))  # 파생: 잔여반영감축량(MIN(기준감축량, 가중합), 부록 L)
    expected_payout = Column(Numeric(15, 2))  # 파생: 예상지급액(부록 L 정본 산식, 단가 미사용)
    client_vehicle_id = Column(
        String(50),
        ForeignKey("tb_client_vehicle.vehicle_id", ondelete="SET NULL"),
    )  # fleet 마스터 링크(참여 구분)
    memo = Column(String(255))
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class ClientVehicle(Base):
    """운수사 보유 차량(fleet) 마스터 — 부록 M. 운수사가 보유한 버스 전량의 원장.

    Docs/BUS_Info_list.xlsx(BUS_LIST_ALL) 컬럼을 반영한다. 식별키는 차대번호(chassis_no)로,
    있으면 UniqueConstraint로 중복을 막는다(nullable → 다중 null 허용). 차량번호(vehicle_no)는
    더는 유일이 아니다(내연+전기 동일번호 공존 가능). 업체명(operator_name)은 엑셀 원문 표기이고
    client_id는 운수사 매칭 결과(미매칭 nullable). 특정 감축사업 참여는 ProjectVehicle이
    client_vehicle_id로 이 마스터를 가리켜 표현한다(참여 구분).
    """

    __tablename__ = "tb_client_vehicle"
    __table_args__ = (UniqueConstraint("chassis_no", name="uq_client_vehicle_chassis"),)

    vehicle_id = Column(String(50), primary_key=True, default=gen_uuid)
    client_id = Column(
        String(50), ForeignKey("tb_client.client_id", ondelete="SET NULL")
    )  # 운수사(업체명 매칭, nullable)
    operator_name = Column(String(100))  # 업체명 원문
    vehicle_no = Column(String(30))  # 차량번호(유일 아님 — 내연/전기 공존 가능)
    region = Column(String(20))  # 차량번호 앞2 파생
    chassis_no = Column(String(50))  # 차대번호
    model_name = Column(String(50))  # 차명
    model_year = Column(Integer)  # 연식
    registered_at = Column(Date)  # 차량등록일
    vehicle_class = Column(String(50))  # 차종
    length_mm = Column(Integer)  # 길이(mm)
    width_mm = Column(Integer)  # 너비(mm)
    height_mm = Column(Integer)  # 높이(mm)
    gross_weight_kg = Column(Integer)  # 총중량(kg)
    seating_capacity = Column(Integer)  # 승차정원
    fuel = Column(String(20))  # 연료
    status = Column(String(20))  # 공통코드 VEHICLE_STATUS: 운행/폐차 (기본 운행은 라우터/기본값)
    asset_id = Column(
        String(50), ForeignKey("tb_asset.asset_id", ondelete="SET NULL")
    )  # 선택 관제 연결
    memo = Column(String(255))
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class FleetStatus(Base):
    """운수사 계약대수 월별 현황(원본 엑셀 유래) — 매월 발행 데이터 업로드로 갱신.

    (고객사 × 월) 단위 스냅샷. 같은 회사 다중 사업장 행은 업로드 시 합산해 1행으로 저장한다.
    미매칭(지역+회사명으로 고객사 못 찾음)은 client_id NULL로 보류. 수작업 관리(대상여부·
    계약여부 등)는 tb_fleet_mgmt에 분리 저장돼 이 테이블 재업로드에 영향받지 않는다.
    """

    __tablename__ = "tb_fleet_status"

    fleet_status_id = Column(String(50), primary_key=True, default=gen_uuid)
    client_id = Column(
        String(50), ForeignKey("tb_client.client_id", ondelete="SET NULL")
    )  # 운수사(지역+회사명 매칭, 미매칭이면 NULL)
    region = Column(String(20))  # 조합(지역)
    industry = Column(String(20))  # 업종(FLEET_INDUSTRY: 시내/농어촌/시외)
    company_name = Column(String(100))  # 원본 회사명(정제 전 원문 보존)
    period = Column(String(7))  # 대상 월 'YYYY-MM'
    license_count = Column(Integer)  # 면허대수
    total_count = Column(Integer)  # 계
    diesel = Column(Integer)  # 경유
    cng = Column(Integer)  # CNG
    hybrid = Column(Integer)  # HB(하이브리드)
    electric = Column(Integer)  # 전기
    hydrogen = Column(Integer)  # 수소
    source = Column(String(20), default="EXCEL")
    created_by = Column(String(50))
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        # (고객사, 월) upsert 유일 — 미매칭(client_id NULL)은 회사명으로 구분
        UniqueConstraint(
            "client_id", "period", "company_name", name="uq_fleet_status_client_period"
        ),
    )


class FleetMgmt(Base):
    """운수사 계약대수 수작업 관리(고객사 1:1) — 대상여부·계약여부 등. 업로드 무영향.

    원본 대수(tb_fleet_status)와 분리해 매월 재업로드가 수작업을 덮지 않게 한다.
    고객사 상세 '현황' 탭에서 편집한다.
    """

    __tablename__ = "tb_fleet_mgmt"

    client_id = Column(
        String(50),
        ForeignKey("tb_client.client_id", ondelete="CASCADE"),
        primary_key=True,
    )
    # 분류값은 현황 탭에서 자동 반영 + 앱 편집. Y/N보다 풍부해 코드로 관리(tb_code, 하드코딩 금지).
    target_type = Column(String(20))  # 대상여부 FLEET_TARGET: BIZ(사업대상)/REG(규제대상)
    contract_status = Column(String(20))  # 계약여부 FLEET_CONTRACT: DONE/NONE/EXCLUDED/REVIEW
    union_contract = Column(String(20))  # 조합계약 FLEET_UNION: REP(대표계약)/MOU
    regulated_type = Column(String(20))  # 규제여부 FLEET_REGULATED: ALLOC(할당)/GOAL(목표)/PUBLIC(공공)
    memo = Column(String(255))
    updated_by = Column(String(50))
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class AccessGroup(Base):
    """접근 그룹(부서·경영진) — 메뉴(화면) 접근 축 (ACCESS_CONTROL_PLAN G1).

    role(직급)은 행위 권한 그대로 두고, 그룹은 '어떤 메뉴가 보이고 접근되는가'만 담당한다.
    is_default(전사) 그룹은 그룹 미배정 사용자의 암묵 소속(fail-safe) — 삭제 금지.
    """

    __tablename__ = "tb_access_group"

    group_id = Column(String(50), primary_key=True, default=gen_uuid)
    name = Column(String(50), nullable=False, unique=True)
    # 부서 코드(tb_code DEPT, nullable) — 지정 시 표시명은 코드 라벨을 따른다(부서명 변경은
    # 공통코드 관리 한 곳에서). 미지정이면 name 자유 텍스트(전사 등 비부서 그룹).
    dept_code = Column(String(30))
    home_path = Column(String(50), default="/dashboard")  # 로그인 자동 랜딩 경로
    is_default = Column(Boolean, nullable=False, default=False)  # 전사(기본) 여부
    memo = Column(String(200))
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class GroupMenu(Base):
    """그룹 × 허용 메뉴 — menu_key는 access_control.MENU_KEYS(nav 경로) 정본."""

    __tablename__ = "tb_group_menu"

    group_id = Column(
        String(50),
        ForeignKey("tb_access_group.group_id", ondelete="CASCADE"),
        primary_key=True,
    )
    menu_key = Column(String(50), primary_key=True)


class UserGroup(Base):
    """사용자 × 그룹 (N:M) — 겸직 허용, 허용 메뉴는 소속 그룹의 합집합."""

    __tablename__ = "tb_user_group"

    user_id = Column(
        String(50), ForeignKey("tb_user.user_id", ondelete="CASCADE"), primary_key=True
    )
    group_id = Column(
        String(50),
        ForeignKey("tb_access_group.group_id", ondelete="CASCADE"),
        primary_key=True,
    )


class Buyer(Base):
    """매수자 마스터(증권/투자/금융사) — 투자·금융사 신원의 근본(Phase 4 INC-1, 부록 N.8 D1).

    기존 ProjectSale.buyer_name(free-text)은 전환기 동안 유지하고, 거래계약이 buyer_id로
    이 마스터를 참조한다(비파괴 additive). buyer_type은 SALE_BUYER_TYPE 공통코드 재사용.
    """

    __tablename__ = "tb_buyer"

    buyer_id = Column(String(50), primary_key=True, default=gen_uuid)
    name = Column(String(100), nullable=False)  # 매수자명(증권/투자/금융사)
    buyer_type = Column(String(20))  # SALE_BUYER_TYPE 공통코드(증권사/투자사/금융사/기타)
    biz_reg_no = Column(String(20))
    contact_name = Column(String(50))
    contact_phone = Column(String(20))
    contact_email = Column(String(100))
    memo = Column(String(255))
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (UniqueConstraint("name", name="uq_buyer_name"),)


class ProjectSale(Base):
    """거래계약(매수자별 선물 판매) — 프로젝트당 매수자 여럿(증권/투자/금융). 판매 단가는
    프로젝트 단일이 아니라 계약 단위로 관리한다(지급 max_payment와 별개 축).

    차액 수익 = Σ(판매단가 × 수량) − Σ(차량 expected_payout)은 저장하지 않고 상세에서 파생.
    """

    __tablename__ = "tb_project_sale"

    sale_id = Column(String(50), primary_key=True, default=gen_uuid)
    project_id = Column(
        String(50),
        ForeignKey("tb_project.project_id", ondelete="CASCADE"),
        nullable=False,
    )
    buyer_name = Column(String(100), nullable=False)  # 매수자(증권/투자/금융) — 전환기 유지
    buyer_type = Column(String(20))  # SALE_BUYER_TYPE 공통코드(증권사/투자사/금융사/기타)
    # 매수자 마스터 링크(부록 N.8 D1) — nullable(전환기). 마스터 삭제 시 SET NULL로 자동 해제.
    buyer_id = Column(
        String(50), ForeignKey("tb_buyer.buyer_id", ondelete="SET NULL")
    )
    sale_unit_price = Column(Numeric(15, 2))  # 선물 판매 톤당 단가(정보성 유지)
    quantity = Column(Numeric(14, 3))  # 판매 수량(tCO2, 정보성 유지)
    # 회계 원장층(부록 L.3) — 매출인식 기준: 실발행액 × 지급률
    ownership_pct = Column(Numeric(5, 2))  # 소유권비율(%)
    sale_invoice_amount = Column(Numeric(15, 2))  # 매출세금계산서 실발행액 — 매출인식 기준
    sale_invoice_date = Column(Date)  # 매출세금계산서 발행일
    sale_payment_date = Column(Date)  # 매출세금계산서 입금일(정보성, nullable)
    sale_approval_no = Column(String(30))  # 국세청 승인번호(24자리) — HTML 자동반영 멱등/중복방지 키
    is_hold = Column(String(1), default="N")  # 후시보유 여부(Y/N)
    contract_date = Column(Date)
    memo = Column(String(255))
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class PurchaseInvoice(Base):
    """매입세금계산서(운수사 실지급=제품) — 회계 원장층(부록 L.3)의 제품(총매입) 원천.

    프로젝트×운수사 분할 다건 허용. 제품(총매입) = Σ amount는 저장하지 않고 상세에서 파생한다.
    operator_name은 엑셀 일괄 등록용 운수사 표기(client_id 매핑과 병용).
    """

    __tablename__ = "tb_purchase_invoice"

    invoice_id = Column(String(50), primary_key=True, default=gen_uuid)
    project_id = Column(
        String(50),
        ForeignKey("tb_project.project_id", ondelete="CASCADE"),
        nullable=False,
    )
    client_id = Column(
        String(50), ForeignKey("tb_client.client_id", ondelete="SET NULL")
    )  # 운수사
    operator_name = Column(String(100))  # 운수사 표기(엑셀 import용)
    region = Column(String(20))
    issue_date = Column(Date)  # 발행일
    payment_date = Column(Date)  # 입금일(정보성, nullable)
    amount = Column(Numeric(15, 2))  # 금액
    approval_no = Column(String(30))  # 국세청 승인번호(24자리) — HTML 자동반영 멱등/중복방지 키
    memo = Column(String(255))
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class TaxInvoice(Base):
    """세금계산서 원장 — 홈택스 보안메일 HTML 자동반영으로 적재하는 후시 전체 세금계산서.

    매입(일반 매입처 포함)·매출을 방향 무관하게 담는 버도 원장(프로젝트 매입/매출과 별개
    상위 원천). 국세청 승인번호(IssueID)로 멱등/중복방지(unique). 상대(자사 아닌 쪽)가 관리
    마스터에 있으면 운수사/투자사로 링크(nullable), 프로젝트 연결도 nullable(추후).
    금액은 공급가액(부가세 제외)이 원가/매출 접점. 수정/취소분은 음수 금액으로 적재된다.
    """

    __tablename__ = "tb_tax_invoice"

    tax_invoice_id = Column(String(50), primary_key=True, default=gen_uuid)
    approval_no = Column(String(30))  # 국세청 승인번호(IssueID) — 멱등/중복방지 키
    direction = Column(String(10))  # 매입/매출/미상
    invoicer_reg_no = Column(String(20))  # 공급자 사업자번호
    invoicee_reg_no = Column(String(20))  # 공급받는자 사업자번호
    invoicer_name = Column(String(100))  # 공급자 상호
    invoicee_name = Column(String(100))  # 공급받는자 상호
    counterpart_reg_no = Column(String(20))  # 자사 아닌 상대 사업자번호
    counterpart_name = Column(String(100))
    issue_date = Column(Date)  # 작성일자
    supply_amount = Column(Numeric(15, 2))  # 공급가액(부가세 제외)
    tax_amount = Column(Numeric(15, 2))  # 세액
    total_amount = Column(Numeric(15, 2))  # 합계
    type_code = Column(String(10))  # 국세청 TypeCode(0101 등)
    purpose_code = Column(String(10))  # PurposeCode(청구/영수/수정 등)
    # 매칭·연결(nullable) — 마스터 삭제 시 SET NULL로 자동 해제
    matched_client_id = Column(
        String(50), ForeignKey("tb_client.client_id", ondelete="SET NULL")
    )
    matched_buyer_id = Column(
        String(50), ForeignKey("tb_buyer.buyer_id", ondelete="SET NULL")
    )
    project_id = Column(
        String(50), ForeignKey("tb_project.project_id", ondelete="SET NULL")
    )
    source = Column(String(20), default="HTML_IMPORT")  # 적재 출처
    memo = Column(String(255))
    created_by = Column(String(50))
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint("approval_no", name="uq_tax_invoice_approval_no"),
    )


class MarketRate(Base):
    """매출단가 시세 마스터(effective-dated) — 탄소배출권 톤당 단가의 시점별 이력.

    현재 시세 = 유효일자(effective_date) ≤ 오늘 중 가장 최신 1건의 unit_price.
    이력 보존이 목적이라 같은 effective_date 재등록은 append 허용(조회는 최신 우선).
    실현매출·회계 원장(부록 L.3)과 무관한 참조성 마스터다(과거 불변).
    """

    __tablename__ = "tb_market_rate"

    rate_id = Column(String(50), primary_key=True, default=gen_uuid)
    effective_date = Column(Date, nullable=False, index=True)  # 시세 유효 시작일
    unit_price = Column(Numeric(15, 2), nullable=False)  # 톤당 단가
    note = Column(String(255))
    created_by = Column(String(50), ForeignKey("tb_user.user_id"))  # 등록자(불변)
    created_at = Column(DateTime, default=utcnow)


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
    # 레거시 정산 매핑(tb_project_client_map) 은퇴 후 순수 감사값 — 과거 map_id 문자열 보존.
    # P4 정산 재건: settlement_id(tb_settlement PK) 보관에 재사용(스키마 변경 0, 그레인 감사키).
    map_id = Column(String(50), nullable=False)
    seq = Column(Integer, nullable=False)
    # 5요소 동결
    issued_credits = Column(Numeric(10, 2))
    amount = Column(Numeric(15, 2))
    unit_price = Column(Numeric(15, 2))
    allocation_ratio = Column(Numeric(5, 2))
    success_fee_rate = Column(Numeric(5, 2))
    paid_amount = Column(Numeric(15, 2))
    # P4 정산 재건: 확정 시점 동결 지표(additive) — 차량 대수·유효감축량
    vehicle_count = Column(Integer)
    effective_reduction = Column(Numeric(14, 3))
    action = Column(String(20), nullable=False)  # CONFIRMED/BILLED/REBILLED/REVERTED/COMPLETED
    reason = Column(String(200))
    created_by = Column(String(50), ForeignKey("tb_user.user_id"))
    created_at = Column(DateTime, default=utcnow)


class Settlement(Base):
    """정산 헤더 — P4 정산 재건. 그레인 = (client_id × project_id). 예정은 lazy(header 없음),
    최초 확정 시 1건 생성. 상태전이 머신 CONFIRMED→BILLED→COMPLETED(코드 SETTLEMENT_STATUS)."""

    __tablename__ = "tb_settlement"
    __table_args__ = (
        # (고객사, 사업, 기간) 단일 헤더 — 중복 확정 차단. period 미지정은 '' sentinel로 저장
        # (라우터 confirm) — PG 유니크가 NULL을 distinct 취급해 NULL 중복을 못 막는 함정 회피.
        UniqueConstraint(
            "client_id", "project_id", "period", name="uq_settlement_client_project_period"
        ),
    )

    settlement_id = Column(String(50), primary_key=True, default=gen_uuid)
    client_id = Column(String(50), ForeignKey("tb_client.client_id"), nullable=False)
    project_id = Column(String(50), ForeignKey("tb_project.project_id"), nullable=False)
    period = Column(String(7), nullable=True)  # 'YYYY-MM' — 단일 정산이면 null
    # 최초 생성이 곧 확정 — 상태값 문자열(코드 SETTLEMENT_STATUS, 하드코딩 금지)
    status = Column(String(20), nullable=False, default="CONFIRMED")
    confirmed_amount = Column(Numeric(15, 2))  # 확정 청구액
    vehicle_count = Column(Integer)  # 확정 시점 차량 대수(동결)
    effective_reduction = Column(Numeric(14, 3))  # 확정 시점 유효감축량(동결)
    confirmed_at = Column(DateTime)
    confirmed_by = Column(String(50), ForeignKey("tb_user.user_id"))
    billed_at = Column(DateTime)
    billed_by = Column(String(50), ForeignKey("tb_user.user_id"))
    completed_at = Column(DateTime)
    completed_by = Column(String(50), ForeignKey("tb_user.user_id"))
    paid_amount = Column(Numeric(15, 2), nullable=True)  # 실입금액(완료 시)
    payment_type = Column(String(20), nullable=True)  # 지급 구분(코드값)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


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
    merge_rule = Column(Text)  # mail-merge 규칙 JSON {folder_code, name_contains} (없으면 null)
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


class ProjectParticipationSnapshot(Base):
    """운수사 참여 집계 변동 이력(append-only) — Phase 4 INC-3, 부록 N.8 D5.

    파생값(effective_reduction·expected_payout)은 제자리 계산을 유지(불변)하고,
    변동 시점에만 (project, client) 그레인으로 스냅샷을 append한다. 직전 스냅샷과
    값이 동일하면 기록하지 않는다(dedup). client_id는 미지정(미매칭) 운수사를 허용.
    """

    __tablename__ = "tb_project_participation_snapshot"

    snapshot_id = Column(String(50), primary_key=True, default=gen_uuid)
    project_id = Column(
        String(50),
        ForeignKey("tb_project.project_id", ondelete="CASCADE"),
        nullable=False,
    )
    client_id = Column(String(50), nullable=True)  # 운수사(미지정 허용) — FK 미설정
    captured_at = Column(DateTime, default=utcnow)  # 변동 포착 시점
    effective_reduction_sum = Column(Numeric(14, 3))  # Σ 잔여반영감축량
    expected_payout_sum = Column(Numeric(15, 2))  # Σ 예상지급액
    trigger = Column(String(30))  # 변동 유발(payout_params/vehicle_cud 등)
    created_at = Column(DateTime, default=utcnow)


class ProjectSaleSnapshot(Base):
    """거래계약(매출) 변동 이력(append-only) — Phase 4 INC-3, 부록 N.8 D5.

    ProjectSale 각 계약을 (project, sale) 그레인으로 변동 시점에만 append한다.
    gross_revenue는 실발행액 우선, 없으면 단가×수량, 둘 다 없으면 None. dedup 동일.
    """

    __tablename__ = "tb_project_sale_snapshot"

    snapshot_id = Column(String(50), primary_key=True, default=gen_uuid)
    project_id = Column(
        String(50),
        ForeignKey("tb_project.project_id", ondelete="CASCADE"),
        nullable=False,
    )
    sale_id = Column(String(50), nullable=True)  # 거래계약(삭제 대비 FK 미설정)
    buyer_id = Column(String(50), nullable=True)  # 매수자(정보성)
    captured_at = Column(DateTime, default=utcnow)  # 변동 포착 시점
    quantity = Column(Numeric(14, 3))  # 판매 수량(tCO2)
    gross_revenue = Column(Numeric(15, 2))  # 총매출(실발행액 우선)
    trigger = Column(String(30))  # 변동 유발(sale_cud 등)
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
        # 운수사 명부(민원대응 회원명부) 추가 정보
        ("tb_client", "fax", "VARCHAR(20)"),
        ("tb_client", "corp_reg_no", "VARCHAR(20)"),
        ("tb_client", "license_date", "DATE"),
        ("tb_client", "bus_city", "INTEGER"),
        ("tb_client", "bus_rural", "INTEGER"),
        ("tb_client", "bus_intercity", "INTEGER"),
        ("tb_segment_send", "merge_rule", "TEXT"),
        ("tb_project", "max_payment", "NUMERIC(15,2)"),
        ("tb_project", "base_reduction", "NUMERIC(10,3)"),
        ("tb_project", "base_vehicle_age", "NUMERIC(5,2)"),
        ("tb_project", "approved_at", "DATE"),
        ("tb_project", "approval_status", "VARCHAR(20)"),
        ("tb_project_vehicle", "expire_at", "DATE"),
        ("tb_project_vehicle", "remaining_age", "NUMERIC(6,3)"),
        ("tb_project_vehicle", "effective_reduction", "NUMERIC(14,3)"),
        ("tb_project_vehicle", "client_vehicle_id", "VARCHAR(50)"),  # fleet 마스터 링크(부록 M)
        # 회계 원장층(부록 L.3) — 거래계약 매출인식 확장 필드
        ("tb_project_sale", "ownership_pct", "NUMERIC(5,2)"),
        ("tb_project_sale", "sale_invoice_amount", "NUMERIC(15,2)"),
        ("tb_project_sale", "sale_invoice_date", "DATE"),
        ("tb_project_sale", "sale_payment_date", "DATE"),
        ("tb_purchase_invoice", "payment_date", "DATE"),
        ("tb_project_sale", "is_hold", "VARCHAR(1)"),
        # 세금계산서 HTML 자동반영(P1) — 국세청 승인번호 멱등키. nullable·유니크 제약 없음
        ("tb_purchase_invoice", "approval_no", "VARCHAR(30)"),
        ("tb_project_sale", "sale_approval_no", "VARCHAR(30)"),
        # 매수자 마스터 링크(부록 N.8 D1) — 비파괴 additive(전환기)
        ("tb_project_sale", "buyer_id", "VARCHAR(50)"),
        # 외부역할 계정 연결(부록 N.8 D3) — PARTNER=운수사, INVESTOR=매수자
        ("tb_user", "client_id", "VARCHAR(50)"),
        ("tb_user", "buyer_id", "VARCHAR(50)"),
        # 외부 포털 매직링크 알림톡 발송 대상(INC-9) — nullable, FK 없음
        ("tb_user", "phone", "VARCHAR(20)"),
        # P4 정산 재건 — 스냅샷 확정 지표 동결(additive 재활용). 배포 PG 조회 500 방지.
        ("tb_settlement_snapshot", "vehicle_count", "INTEGER"),
        ("tb_settlement_snapshot", "effective_reduction", "NUMERIC(14,3)"),
        # 운수사 계약대수 수작업 분류 확장(F6) — 현황 탭 자동 반영. 기존 Y/N 컬럼은 레거시로 잔존.
        ("tb_fleet_mgmt", "contract_status", "VARCHAR(20)"),
        ("tb_fleet_mgmt", "regulated_type", "VARCHAR(20)"),
        # 접근 그룹 부서코드 연동 — 부서명은 공통코드(DEPT)에서 관리
        ("tb_access_group", "dept_code", "VARCHAR(30)"),
        # 외부 포털 이용권 만료(1일/1주/1개월/연간권)
        ("tb_user", "portal_expires_at", "TIMESTAMP"),
    ]
    try:
        insp = _inspect(engine)
        tables = set(insp.get_table_names())
        for table, column, ddl in required:
            if table not in tables:
                continue
            cols = {c["name"] for c in insp.get_columns(table)}
            if column not in cols:
                # PostgreSQL은 IF NOT EXISTS로 다중 인스턴스 동시 배포 TOCTOU 경합 창 제거
                # (inspector 확인 후 ALTER 사이 다른 인스턴스가 먼저 추가해도 안전).
                # SQLite는 IF NOT EXISTS ADD COLUMN 미지원 → 위 inspector 사전확인만 의존.
                add_kw = "ADD COLUMN IF NOT EXISTS" if engine.dialect.name == "postgresql" else "ADD COLUMN"
                with engine.begin() as conn:
                    conn.execute(_text("ALTER TABLE {0} {1} {2} {3}".format(table, add_kw, column, ddl)))
                print("✓ Added missing column {0}.{1}".format(table, column))
    except Exception as exc:
        # 컬럼 보강 실패는 부분 스키마를 방치할 수 있어(누락 컬럼 → 조회 500) 명확히 경고.
        # 부팅은 유지(크래시 방지)하되 로그에서 반드시 눈에 띄게 남긴다.
        print("‼ ensure_schema COLUMN 보강 실패 — 스키마 부분적용 가능, 즉시 확인 필요: {0}".format(exc))

    # 배포된 테이블에 유니크 인덱스 보강 (P0-B) — create_all은 기존 테이블에 제약을
    # 추가하지 않음. 신규 DB는 __table_args__의 UniqueConstraint로 생성되므로 동일
    # 컬럼 유니크가 이미 있으면 건너뛴다 (SQLite/PostgreSQL 공통 표준 구문).
    # (index_name, table, 컬럼 목록) — NULL 다수 컬럼이어도 유니크 충돌 없음
    unique_indexes = [
        # 보고서 버전 max+1 동시 계산 경합 방지 (P0-B)
        ("uq_document_report_version", "tb_document", ["report_id", "version"]),
        # 정산 회차 seq max+1 동시 계산 경합 방지 (P0-B 준용, R3-1)
        ("uq_settlement_snapshot_map_seq", "tb_settlement_snapshot", ["map_id", "seq"]),
        # 같은 (사업, 단계코드) 중복 시드 방지 — 배포형 DB 단계 중복행 예방 (정교화 P0)
        ("uq_project_stage_slot", "tb_project_stage", ["project_id", "stage_code"]),
        # 운수사 보유 차량 마스터 — 식별키 차대번호 유일(부록 M, nullable 다중 null 허용)
        ("uq_client_vehicle_chassis", "tb_client_vehicle", ["chassis_no"]),
        # 매수자 마스터 — 매수자명 유일(부록 N.8 D1). 배포형 DB 보강(신규는 __table_args__)
        ("uq_buyer_name", "tb_buyer", ["name"]),
        # P4 정산 재건 — (고객사, 사업, 기간) 정산 헤더 유일(신규는 __table_args__, 배포형 보강)
        ("uq_settlement_client_project_period", "tb_settlement", ["client_id", "project_id", "period"]),
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
        # 5) 원가/fleet 축(~5,200행) — 사업상세·고객사목록·보유차량탭 집계 (DBA P0)
        ("ix_pv_project", "tb_project_vehicle", ["project_id"]),
        ("ix_pv_client", "tb_project_vehicle", ["client_id"]),
        ("ix_pv_cvid", "tb_project_vehicle", ["client_vehicle_id"]),
        ("ix_pv_vehicle_no", "tb_project_vehicle", ["vehicle_no"]),
        ("ix_cv_client", "tb_client_vehicle", ["client_id"]),
        ("ix_cv_vehicle_no", "tb_client_vehicle", ["vehicle_no"]),
        # 6) 원장/정산 축 — client_id 선행 group·project_id 필터 (DBA P1)
        ("ix_sale_project", "tb_project_sale", ["project_id"]),
        ("ix_pinv_project", "tb_purchase_invoice", ["project_id"]),
        # 7) 변동 이력 스냅샷(append-only, INC-3) — 타임라인 조회 대비(project·client 그레인)
        ("ix_ppsnap_project_client", "tb_project_participation_snapshot", ["project_id", "client_id"]),
        ("ix_pssnap_project", "tb_project_sale_snapshot", ["project_id"]),
        # 8) 세금계산서 원장(홈택스 HTML) — 방향/기간 조회·매칭 조인 (DBA P1)
        ("ix_ti_direction_date", "tb_tax_invoice", ["direction", "issue_date"]),
        ("ix_ti_client", "tb_tax_invoice", ["matched_client_id"]),
        ("ix_ti_buyer", "tb_tax_invoice", ["matched_buyer_id"]),
        ("ix_ti_project", "tb_tax_invoice", ["project_id"]),
        # 9) 고객사 upsert·대기/정식 판정 후보 축소 — 사업자번호·회사명 (DBA P1)
        ("ix_client_biz", "tb_client", ["biz_reg_no"]),
        ("ix_client_company", "tb_client", ["company_name"]),
        # 10) 정산 헤더 조회 — 고객사·사업 필터 (DBA P1)
        ("ix_settlement_client", "tb_settlement", ["client_id"]),
        ("ix_settlement_project", "tb_settlement", ["project_id"]),
        # 11) 운수사 계약대수 현황 — 고객사별 추이·월별 집계
        ("ix_fleet_status_client", "tb_fleet_status", ["client_id"]),
        ("ix_fleet_status_period", "tb_fleet_status", ["period"]),
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

    # 구(舊) 차량번호 유니크 제약 제거 — 식별키가 차대번호로 바뀌면서 vehicle_no 유일성
    # 폐기(내연+전기 동일번호 공존). PostgreSQL 배포형 DB에 남은 제약을 떨어뜨린다.
    # SQLite/방언차·미존재는 무시(try/except) — DROP CONSTRAINT IF EXISTS는 PG 전용 구문.
    try:
        with engine.begin() as conn:
            conn.execute(
                _text("ALTER TABLE tb_client_vehicle DROP CONSTRAINT IF EXISTS uq_client_vehicle_no")
            )
    except Exception as exc:
        print("⚠ ensure_schema drop legacy constraint skipped: {0}".format(exc))

    # 사용자 이메일 유니크 해제 — 배포 DB의 유니크 인덱스를 일반 인덱스로 재생성(멱등:
    # 유니크일 때만 수행). 외부 포털 다중 계정(같은 이메일) 허용의 전제.
    try:
        insp2 = _inspect(engine)
        for ix in insp2.get_indexes("tb_user"):
            if ix.get("column_names") == ["email"] and ix.get("unique"):
                with engine.begin() as conn:
                    conn.execute(_text('DROP INDEX IF EXISTS "{0}"'.format(ix["name"])))
                    conn.execute(_text(
                        'CREATE INDEX IF NOT EXISTS ix_tb_user_email ON tb_user (email)'
                    ))
                print("✓ tb_user.email unique index → non-unique 재생성")
        # 컬럼 유니크 제약으로 배포된 경우(tb_user_email_key)도 제거 (PG 전용 구문은 방언 가드)
        if engine.dialect.name == "postgresql":
            for uc in insp2.get_unique_constraints("tb_user"):
                if uc.get("column_names") == ["email"]:
                    with engine.begin() as conn:
                        conn.execute(_text(
                            'ALTER TABLE tb_user DROP CONSTRAINT IF EXISTS "{0}"'.format(uc["name"])
                        ))
                    print("✓ tb_user.email unique constraint 제거")
    except Exception as exc:
        print("⚠ ensure_schema email unique 하향 skipped: {0}".format(exc))

    # 운수사 조합계약 컬럼 폭 확대(F6) — 기존 VARCHAR(1)로 배포된 dev에서 '대표계약'(코드 REP는
    # 짧지만 라벨/코드 확장 여지) 저장 가능하게 넓힘. PG 전용·멱등(빈 테이블 안전). SQLite는 길이 무시.
    if engine.dialect.name == "postgresql":
        try:
            with engine.begin() as conn:
                conn.execute(
                    _text("ALTER TABLE tb_fleet_mgmt ALTER COLUMN union_contract TYPE VARCHAR(20)")
                )
        except Exception as exc:
            print("⚠ ensure_schema widen union_contract skipped: {0}".format(exc))

    _reconcile_fk_ondelete(engine)


# FK ondelete 정책표(정본) — 모델 정의와 동일. 구(舊) 배포 DB가 이 규칙 이전에 생성돼
# NO ACTION으로 남은 FK를 배포 시 자동 교정한다(DBA P0). (table, col, ref_table, ref_col, ondelete)
_FK_ONDELETE_SPECS = [
    ("tb_project_vehicle", "project_id", "tb_project", "project_id", "CASCADE"),
    ("tb_project_vehicle", "client_id", "tb_client", "client_id", "SET NULL"),
    ("tb_project_vehicle", "asset_id", "tb_asset", "asset_id", "SET NULL"),
    ("tb_project_vehicle", "client_vehicle_id", "tb_client_vehicle", "vehicle_id", "SET NULL"),
    ("tb_project_sale", "project_id", "tb_project", "project_id", "CASCADE"),
    ("tb_project_sale", "buyer_id", "tb_buyer", "buyer_id", "SET NULL"),
    ("tb_purchase_invoice", "project_id", "tb_project", "project_id", "CASCADE"),
    ("tb_purchase_invoice", "client_id", "tb_client", "client_id", "SET NULL"),
    ("tb_project_stage", "project_id", "tb_project", "project_id", "CASCADE"),
    ("tb_client_vehicle", "client_id", "tb_client", "client_id", "SET NULL"),
    ("tb_client_vehicle", "asset_id", "tb_asset", "asset_id", "SET NULL"),
    ("tb_user", "client_id", "tb_client", "client_id", "SET NULL"),
    ("tb_user", "buyer_id", "tb_buyer", "buyer_id", "SET NULL"),
]


def _reconcile_fk_ondelete(engine):
    """구 배포 DB의 FK ondelete를 정책표에 맞게 멱등 교정(PostgreSQL 전용).

    현재 ondelete를 inspector로 확인해 **불일치일 때만** 제약을 DROP 후 재생성한다.
    이미 정합이면 no-op. SQLite는 ALTER로 FK 변경이 불가하므로 통째로 건너뛴다(no-op).
    실패는 삼켜 부팅을 막지 않는다(다른 ensure_schema 단계와 동일 규약).
    """
    if engine.dialect.name != "postgresql":
        return
    from sqlalchemy import inspect as _inspect, text as _text
    _NORM = {"CASCADE": "CASCADE", "SET NULL": "SET NULL", "SETNULL": "SET NULL", None: "NO ACTION", "NO ACTION": "NO ACTION"}
    try:
        insp = _inspect(engine)
        tables = set(insp.get_table_names())
    except Exception as exc:
        print("⚠ ensure_schema fk reconcile inspect skipped: {0}".format(exc))
        return
    for table, col, rt, rc, want in _FK_ONDELETE_SPECS:
        if table not in tables or rt not in tables:
            continue
        try:
            fks = insp.get_foreign_keys(table)
            match = next((fk for fk in fks if fk.get("constrained_columns") == [col]), None)
            if match is None:
                continue  # FK 자체가 없으면 건드리지 않음(모델/마이그레이션 소관)
            cur = (match.get("options") or {}).get("ondelete")
            cur_norm = _NORM.get((cur or "").upper() if cur else None, "NO ACTION")
            if cur_norm == want:
                continue  # 이미 정합 — no-op(멱등)
            name = match.get("name")
            if not name:
                continue
            with engine.begin() as conn:
                conn.execute(_text('ALTER TABLE {0} DROP CONSTRAINT IF EXISTS "{1}"'.format(table, name)))
                conn.execute(_text(
                    'ALTER TABLE {0} ADD CONSTRAINT "{1}" FOREIGN KEY ("{2}") '
                    'REFERENCES {3} ("{4}") ON DELETE {5}'.format(table, name, col, rt, rc, want)
                ))
            print("✓ Reconciled FK {0}.{1} -> ON DELETE {2}".format(table, col, want))
        except Exception as exc:
            print("⚠ ensure_schema fk reconcile skipped ({0}.{1}): {2}".format(table, col, exc))


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
