"""운수사 표준 통합 양식(transport) — 전 컬럼·upsert·과잉정제 방지."""

import io
import os

import openpyxl
import pytest

import models
from services import excel_import

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


def test_company_clean_no_overstrip():
    c = excel_import._tf_company_clean
    assert c("(사)제주관광협회") == "제주관광협회"
    assert c("(재)차세대융합기술원") == "차세대융합기술원"
    assert c("다모아자동차(주)") == "다모아자동차"  # 자동차 보존
    assert c("세일교통(자") == "세일교통"  # 잘린 괄호(끝) 제거
    assert c("(사무국)운영") == "(사무국)운영"  # 접두 과잉제거 없음
    assert c("자동차공업사") == "자동차공업사"  # 괄호 없는 '사' 보존


def test_transport_standard_full_columns_and_upsert(client, staff_headers):
    api = "/api/v1/imports/transport/commit"
    db = models.SessionLocal()
    try:
        db.query(models.Client).filter(
            models.Client.company_name.in_(["표준운수A", "표준운수B"])
        ).delete(synchronize_session=False)
        db.commit()
        # 기존(사업자번호 없음)
        db.add(models.Client(client_type="TRANSPORT", company_name="표준운수A", region="서울"))
        db.commit()

        data = _xlsx([
            ["표준운수A(주)", "221-81-00682", "140111-0000105", "강원", "이동진",
             "033-254-8272", "033-253-2304", "강원 춘천시 1", "1970-10-01", 73, 0, 0],
            ["(주)표준운수B", "111-11-11111", None, "경기", "김대표",
             "031-111-1111", "031-111-1112", "경기 수원시 2", "2004-07-01", 10, 5, 0],
        ])
        r = client.post(api, headers=staff_headers,
                        files={"file": ("std.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["updated"] == 1 and body["created"] == 1

        db.expire_all()
        a = db.query(models.Client).filter_by(company_name="표준운수A").first()
        assert a.biz_reg_no == "221-81-00682"  # 보강
        assert a.region == "강원" and str(a.license_date) == "1970-10-01" and a.bus_city == 73
        b = db.query(models.Client).filter_by(company_name="표준운수B").first()
        assert b is not None and b.biz_reg_no == "111-11-11111" and b.bus_rural == 5
    finally:
        db.query(models.Client).filter(
            models.Client.company_name.in_(["표준운수A", "표준운수B"])
        ).delete(synchronize_session=False)
        db.commit()
        db.close()


_MERGED = "/Users/ssh/Documents/Develope/hooxi-cms/Docs/고객사/운수사_고객리스트_표준_통합_260820.xlsx"


@pytest.mark.skipif(not os.path.exists(_MERGED), reason="통합 파일 없음(CI 스킵)")
def test_merged_standard_file_all_valid(client):
    db = models.SessionLocal()
    try:
        res = excel_import.parse_and_validate(db, "transport", open(_MERGED, "rb").read())
        assert len([r for r in res.rows if r.errors]) == 0
        assert len(res.valid_rows) >= 600  # 병합 결과(약 673)
    finally:
        db.close()
