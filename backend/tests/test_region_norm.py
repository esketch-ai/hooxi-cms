"""지역명 표준화(services/region_norm) — 업로드 변환·ensure_schema 데이터 보정.

운영 고객사마스터 업로드에서 정식 행정구역명(경기도·경상남도·제주특별자치도…)이
그대로 저장돼 공통코드 REGION(단축형)과 어긋난 사고(2026-08-24) 회귀 방지.
"""

import io

import openpyxl

import models
from services.region_norm import REGION_FULL_TO_CODE, normalize_region

STD_HEADERS = [
    "회사명", "사업자등록번호", "법인등록번호", "지역", "대표자", "전화", "팩스",
    "주소", "면허일자", "시내", "농어촌", "시외",
]


def _xlsx(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(STD_HEADERS)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_normalize_region_full_names():
    assert normalize_region("경기도") == "경기"
    assert normalize_region("경상남도") == "경남"
    assert normalize_region("제주특별자치도") == "제주"
    assert normalize_region("강원특별자치도") == "강원"
    assert normalize_region("전북특별자치도") == "전북"
    assert normalize_region("세종특별자치시") == "세종"
    assert normalize_region("광주광역시") == "광주"
    assert normalize_region(" 서울특별시 ") == "서울"


def test_normalize_region_suffix_fallback_variants():
    """실존하지 않는 변형 표기(운영 파일 유입)도 접미사 제거로 귀결."""
    assert normalize_region("서울특별자치시") == "서울"
    assert normalize_region("전남광주통합특별시") == "전남광주"
    assert normalize_region("부산특별자치시") == "부산"
    assert normalize_region("경기광역시") == "경기"
    # 귀결 불가한 접미사 제거 결과는 원본 보존
    assert normalize_region("한빛특별시") == "한빛특별시"


def test_normalize_region_idempotent_and_preserves_legacy():
    # 이미 단축형·관용 표기는 그대로(멱등)
    for v in ["서울", "경기", "전남광주", "고속", ""]:
        assert normalize_region(v) == v
    assert normalize_region(None) == ""
    # 표의 모든 결과값은 다시 넣어도 불변(고정점)
    for code in set(REGION_FULL_TO_CODE.values()):
        assert normalize_region(code) == code


def test_transport_import_normalizes_full_region(client, staff_headers):
    """운수사(표준) 업로드에 정식 명칭이 와도 단축형으로 저장된다."""
    api = "/api/v1/imports/transport/commit"
    db = models.SessionLocal()
    try:
        db.query(models.Client).filter(
            models.Client.company_name.in_(["지역정규화운수A", "지역정규화운수B"])
        ).delete(synchronize_session=False)
        db.commit()

        data = _xlsx([
            ["지역정규화운수A", "300-81-00001", None, "경상남도", "김대표",
             "055-111-1111", None, "경상남도 창원시 1", "2000-01-01", 10, 0, 0],
            ["지역정규화운수B", "300-81-00002", None, "제주특별자치도", "이대표",
             "064-111-1111", None, "제주특별자치도 제주시 2", "2000-01-01", 5, 0, 0],
        ])
        res = client.post(
            api, headers=staff_headers,
            files={"file": ("표준.xlsx", data,
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert res.status_code == 200, res.text
        a = db.query(models.Client).filter_by(company_name="지역정규화운수A").one()
        b = db.query(models.Client).filter_by(company_name="지역정규화운수B").one()
        assert a.region == "경남"
        assert b.region == "제주"
    finally:
        db.query(models.Client).filter(
            models.Client.company_name.in_(["지역정규화운수A", "지역정규화운수B"])
        ).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_ensure_schema_normalizes_existing_regions(client):
    """이미 오염된 기존 행(정식 명칭)이 ensure_schema 재실행으로 단축형이 된다(멱등)."""
    db = models.SessionLocal()
    try:
        db.query(models.Client).filter(
            models.Client.company_name == "지역보정대상운수"
        ).delete(synchronize_session=False)
        db.add(models.Client(
            client_type="TRANSPORT", company_name="지역보정대상운수", region="경기도",
        ))
        db.add(models.Client(
            client_type="TRANSPORT", company_name="지역보정변형운수", region="전남광주통합특별시",
        ))
        db.commit()

        models.ensure_schema()

        db.expire_all()
        row = db.query(models.Client).filter_by(company_name="지역보정대상운수").one()
        assert row.region == "경기"
        row2 = db.query(models.Client).filter_by(company_name="지역보정변형운수").one()
        assert row2.region == "전남광주"
        # 재실행해도 불변(멱등)
        models.ensure_schema()
        db.expire_all()
        row = db.query(models.Client).filter_by(company_name="지역보정대상운수").one()
        assert row.region == "경기"
    finally:
        db.query(models.Client).filter(
            models.Client.company_name.in_(["지역보정대상운수", "지역보정변형운수"])
        ).delete(synchronize_session=False)
        db.commit()
        db.close()
