"""엑셀 일괄 등록 컬럼 규격 — 유일한 규격 원천 (SCR-03/04 imports).

양식(.xlsx) 생성·업로드 파싱·행 검증·GET /imports/{entity}/spec 응답이 전부
이 파일의 IMPORT_SPECS에서 파생된다. 컬럼 라벨·순서·예시를 바꾸려면
**이 파일 1곳만** 수정하면 된다(다른 파일 수정 불필요 — test_imports_excel.py의
단일 원천 테스트가 이를 보증).

설계 규칙:
- field는 대상 Pydantic 스키마(ClientCreate/AssetCreate)의 실제 필드명과 1:1
  (test_imports_spec.py가 대조 검증). 셀 값 검증은 스키마에 위임한다.
- code_category가 있으면 tb_code 활성 코드의 라벨/코드 양방향으로 수용.
- resolver는 이름→ID 해석("user_by_name"·"client_by_name").
- 인증 비밀값(auth_value·비밀번호·API 토큰) 컬럼은 절대 추가 금지 —
  평문 비밀값이 엑셀 파일로 유통되는 경로를 원천 차단한다(R2-E6 취지).
  인증정보는 등록 후 자산 화면에서 개별 입력(암호화 저장)한다.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Type

from pydantic import BaseModel

import schemas

# 1회 업로드 행 수 상한 — 초과 시 422 (내부 CMS 규모·행별 검증 비용 기준)
MAX_IMPORT_ROWS = 1000


@dataclass(frozen=True)
class ImportColumn:
    """엑셀 컬럼 1개의 규격 — label(헤더 표기)만 바꿔도 양식·파싱이 함께 따라온다."""

    field: str                                # 대상 스키마 필드명 (resolver 컬럼은 해석 결과가 담길 필드)
    label: str                                # 엑셀 헤더 라벨 (실무진이 바꾸는 지점)
    required: bool = False                    # 필수 여부 — 양식 헤더에 * 표시
    code_category: Optional[str] = None       # tb_code 카테고리 — 라벨/코드 양방향 수용
    resolver: Optional[str] = None            # "user_by_name" | "client_by_name"
    transform: Optional[str] = None           # 값 변환 훅 — "company_clean"|"phone_kr"|"license_date_kr"
    yn: bool = False                          # Y/N 컬럼 (예/아니오·O/X 등 정규화)
    fixed_values: Optional[Dict[str, str]] = None  # 코드 마스터가 아닌 고정값 매핑 (표기→저장값)
    # 양식 예시 행 값. code_category 컬럼은 **불변 코드값**으로 적는다 —
    # 라벨은 관리자가 언제든 바꿀 수 있어(tb_code 설계) 양식 생성 시
    # 현재 활성 라벨로 동적 표시한다(excel_import.build_template).
    example: str = ""


@dataclass(frozen=True)
class ImportSpec:
    """엔티티 1종의 일괄 등록 규격."""

    entity: str                    # URL 세그먼트 (clients/assets)
    label: str                     # 화면 표기명
    schema_cls: Type[BaseModel]    # 행 검증을 위임할 대상 스키마
    columns: Tuple[ImportColumn, ...]
    filename: str                  # 양식 다운로드 파일명 (한글)
    header_row: int = 1            # 헤더가 위치한 행(1-base) — 제목 행이 앞에 있는 실무 양식용


# 인증 방식 — tb_code 카테고리가 아니라 AssetCreate 패턴(^(ID_PW|API_KEY|NONE)$)
# 고정값. 한국어 표기·코드값 모두 수용한다. (AUTH_TYPE 코드 카테고리는 미운영 확인)
_AUTH_TYPE_VALUES = {
    "ID_PW": "ID_PW",
    "아이디/비밀번호": "ID_PW",
    "API_KEY": "API_KEY",
    "API 키": "API_KEY",
    "NONE": "NONE",
    "없음": "NONE",
}


IMPORT_SPECS: Dict[str, ImportSpec] = {
    # ── 고객사 (SCR-03 단건 등록과 동일 효과 — 구독 없이 기본 생성) ──────
    "clients": ImportSpec(
        entity="clients",
        label="고객사",
        schema_cls=schemas.ClientCreate,
        filename="고객사_일괄등록_양식.xlsx",
        columns=(
            ImportColumn("company_name", "회사명", required=True, example="한빛운수"),
            ImportColumn(
                "client_type", "구분", required=True,
                code_category="CLIENT_TYPE", example="TRANSPORT",
            ),
            ImportColumn("biz_reg_no", "사업자번호", example="123-45-67890"),
            ImportColumn("region", "지역", code_category="REGION", example="서울"),
            ImportColumn("address", "주소", example="서울시 강남구 테헤란로 1"),
            ImportColumn("ceo_name", "대표자", example="김대표"),
            ImportColumn("ceo_contact_phone", "대표 연락처", example="010-1234-5678"),
            ImportColumn("ceo_contact_email", "대표 이메일", example="ceo@example.com"),
            ImportColumn("main_contact_name", "주 담당자명", example="박담당"),
            ImportColumn("main_contact_phone", "주 담당자 연락처", example="010-2345-6789"),
            ImportColumn("main_contact_email", "주 담당자 이메일", example="contact@example.com"),
            ImportColumn("keyman", "keyman", example="박담당"),
            ImportColumn(
                "contract_status", "계약 상태",
                code_category="CONTRACT_STATUS", example="ACTIVE",
            ),
            ImportColumn("contract_date", "계약 일자", example="2026-01-15"),
            ImportColumn(
                "manager_id", "담당 PM", resolver="user_by_name", example="관리자",
            ),
            ImportColumn("report_yn", "월간 보고서 수신", yn=True, example="Y"),
        ),
    ),
    # ── 운수사 명부 (민원대응 회원명부 양식 그대로 — client_type=TRANSPORT 고정) ──────
    #    회사명 (주)/㈜/주식회사/(유) 접두·접미 제거, 전화/팩스 형식 정규화, 면허일자 YY.MM.DD 파싱.
    #    조합=지역(자유 텍스트), 대표자 최대 3인(콤마 유지). 시/도·시군구 이하 컬럼은 무시(미매칭).
    "transport_roster": ImportSpec(
        entity="transport_roster",
        label="운수사 명부",
        schema_cls=schemas.TransportRosterCreate,
        filename="운수사_명부_일괄등록_양식.xlsx",
        columns=(
            ImportColumn("company_name", "회사명", required=True,
                         transform="company_clean", example="경성여객"),
            ImportColumn("region", "조합", example="서울"),
            ImportColumn("ceo_name", "대표자", example="김대표, 이대표"),
            ImportColumn("ceo_contact_phone", "전 화", transform="phone_kr", example="02)435-5158"),
            ImportColumn("fax", "FAX", transform="phone_kr", example="02)495-0293"),
            ImportColumn("address", "업체 주소", example="서울특별시 중랑구 용마산로 376"),
            ImportColumn("license_date", "면허일자", transform="license_date_kr", example="70.10.01"),
            ImportColumn("bus_city", "시내", example="73"),
            ImportColumn("bus_rural", "농어촌", example="0"),
            ImportColumn("bus_intercity", "시외", example="0"),
        ),
    ),
    # ── 운수사 정보(정본) — 사업자/법인등록번호 포함, 회사명 매칭 upsert ──────
    #    회사명이 기존 운수사와 일치하면 사업자번호 등 보강(update), 없으면 신규 생성.
    "transport_info": ImportSpec(
        entity="transport_info",
        label="운수사 정보(정본)",
        schema_cls=schemas.TransportRosterCreate,
        filename="운수사_정보_일괄등록_양식.xlsx",
        header_row=2,  # 1행은 '운수회사 목록' 제목, 2행이 컬럼 헤더
        columns=(
            ImportColumn("company_name", "운수회사명", required=True,
                         transform="company_clean", example="강원고속"),
            ImportColumn("region", "조합", transform="union_region", example="강원버스조합"),
            ImportColumn("ceo_name", "대표자명", example="이동진"),
            ImportColumn("corp_reg_no", "법인등록번호", example="140111-0000105"),
            ImportColumn("biz_reg_no", "사업자등록번호", example="221-81-00682"),
            ImportColumn("ceo_contact_phone", "전화번호", transform="phone_kr", example="033-254-8272"),
            ImportColumn("fax", "팩스번호", transform="phone_kr", example="033-253-2304"),
        ),
    ),
    # ── 자산 (SCR-04 단건 등록과 동일 효과 — 인증 비밀값 없이 생성) ──────
    "assets": ImportSpec(
        entity="assets",
        label="자산",
        schema_cls=schemas.AssetCreate,
        filename="자산_일괄등록_양식.xlsx",
        columns=(
            ImportColumn(
                "client_id", "고객사명", required=True,
                resolver="client_by_name", example="한빛운수",
            ),
            ImportColumn(
                "asset_group", "대분류", required=True,
                code_category="ASSET_GROUP", example="MOBILITY",
            ),
            ImportColumn(
                "asset_type", "소분류", code_category="ASSET_TYPE", example="EV",
            ),
            ImportColumn("quantity", "수량", example="10"),
            ImportColumn("main_spec", "주요 제원", example="1톤 전기트럭"),
            ImportColumn("telemetry_yn", "관제 연동", yn=True, example="Y"),
            ImportColumn("location_info", "설치 위치", example="본사 차고지"),
            ImportColumn(
                "status", "운영 상태", code_category="ASSET_STATUS", example="ACTIVE",
            ),
            ImportColumn("agency_name", "대상 기관", example="ETAS"),
            ImportColumn("site_url", "접속 URL", example="https://etas.kotsa.or.kr"),
            ImportColumn(
                "auth_type", "인증 방식",
                fixed_values=_AUTH_TYPE_VALUES, example="아이디/비밀번호",
            ),
            ImportColumn("login_id", "로그인 ID", example="hanbit01"),
            # ⚠ 비밀번호/API 토큰 컬럼 금지 — 파일 상단 모듈 docstring 참조.
            ImportColumn("usage_purpose", "용도", example="운행기록 수집"),
        ),
    ),
    # ── 사업 참여 차량 (Phase 2) — 프로젝트 스코프. project_id는 URL에서 주입(행 컬럼 아님).
    #    total_reduction·expected_payout은 서버 파생(원가단가 × 총감축량, H.4) — 엑셀 수기 유입 없음.
    "project_vehicles": ImportSpec(
        entity="project_vehicles",
        label="사업 참여 차량",
        schema_cls=schemas.ProjectVehicleIn,
        filename="사업참여차량_일괄등록_양식.xlsx",
        columns=(
            ImportColumn("vehicle_no", "차량번호", example="제주79자7011"),
            ImportColumn(
                "client_id", "운수사", resolver="client_by_name", example="한빛운수",
            ),
            ImportColumn(
                "introduction_type", "도입구분",
                code_category="VEHICLE_INTRO", example="신규도입",
            ),
            ImportColumn("region", "지역", code_category="REGION", example="제주"),
            ImportColumn("registered_at", "차량등록일", example="2023-08-14"),
            ImportColumn("reduction_y1", "1차 감축량", example="10.5"),
            ImportColumn("reduction_y2", "2차 감축량", example="10.5"),
            ImportColumn("reduction_y3", "3차 감축량", example="10.5"),
            ImportColumn("reduction_y4", "4차 감축량", example="10.5"),
            ImportColumn("reduction_y5", "5차 감축량", example="10.5"),
            ImportColumn("reduction_y6", "6차 감축량", example="10.5"),
            ImportColumn("reduction_y7", "7차 감축량", example="10.5"),
            ImportColumn("reduction_y8", "8차 감축량", example="10.5"),
            ImportColumn("reduction_y9", "9차 감축량", example="10.5"),
            ImportColumn("reduction_y10", "10차 감축량", example="10.5"),
            ImportColumn("private_invest_ratio", "민간투자비율", example="80"),
            ImportColumn("memo", "비고", example=""),
        ),
    ),
    # ── 매입세금계산서(운수사 실지급=제품) — 회계 원장층(부록 L.3). 프로젝트 스코프.
    #    project_id는 URL에서 주입(행 컬럼 아님). operator_name은 운수사 표기(평문, 매핑 없이 저장).
    "purchase_invoices": ImportSpec(
        entity="purchase_invoices",
        label="매입세금계산서",
        schema_cls=schemas.PurchaseInvoiceIn,
        filename="매입세금계산서_일괄등록_양식.xlsx",
        columns=(
            ImportColumn("operator_name", "운수사", example="한빛운수"),
            ImportColumn("region", "지역", code_category="REGION", example="제주"),
            ImportColumn("issue_date", "발행일", example="2026-01-15"),
            ImportColumn("payment_date", "입금일", example="2026-02-15"),
            ImportColumn("amount", "금액", required=True, example="1000000"),
            ImportColumn("memo", "비고", example=""),
        ),
    ),
}
