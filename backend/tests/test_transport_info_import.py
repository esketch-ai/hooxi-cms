"""운수사 정보(정본) 일괄등록 — header_row=2·회사명 매칭 upsert·사업자/법인번호."""

import io
import os

import openpyxl
import pytest

import models
from services import excel_import

INFO_HEADERS = [
    "No.", "사업자구분", "조합", "운수회사코드", "지역", "관할관청",
    "운수회사명", "대표자명", "법인등록번호", "사업자등록번호", "전화번호", "팩스번호",
]


def _build_info_xlsx(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["운수회사 목록"])  # 1행 제목
    ws.append(INFO_HEADERS)       # 2행 헤더
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_transport_info_header_row2_and_transforms(client):
    data = _build_info_xlsx([
        [1, "법인", "강원버스조합", "00730", "강원특별자치도", "춘천시",
         "강원고속(주)", "이동진", "140111-0000105", "221-81-00682", "033-254-8272", "033-253-2304"],
    ])
    db = models.SessionLocal()
    try:
        res = excel_import.parse_and_validate(db, "transport_info", data)
        assert len(res.valid_rows) == 1 and not [r for r in res.rows if r.errors]
        p = res.valid_rows[0].payload
        assert p.company_name == "강원고속"  # (주) 제거
        assert p.region == "강원"  # 조합→지역
        assert p.biz_reg_no == "221-81-00682"  # 하이픈 원본
        assert p.corp_reg_no == "140111-0000105"
        assert p.client_type == "TRANSPORT"
    finally:
        db.close()


def test_transport_info_upsert(client, staff_headers):
    api = "/api/v1/imports/transport_info/commit"
    db = models.SessionLocal()
    try:
        db.query(models.Client).filter(models.Client.company_name == "테스트정본운수").delete(
            synchronize_session=False
        )
        db.commit()
        # 사업자번호 없는 기존 운수사(명부 등록분 모사)
        c = models.Client(client_type="TRANSPORT", company_name="테스트정본운수", region="강원")
        db.add(c)
        db.commit()
        cid = c.client_id

        data = _build_info_xlsx([
            [1, "법인", "강원버스조합", "00730", "강원특별자치도", "춘천시",
             "테스트정본운수(주)", "이동진", "140111-0000105", "221-81-00682", "033-254-8272", "033-253-2304"],
            [2, "법인", "경기버스조합", "00001", "경기도", "수원시",
             "신규정본운수(주)", "김대표", "111111-0000000", "111-11-11111", "031-111-1111", "031-111-1112"],
        ])
        r = client.post(api, headers=staff_headers,
                        files={"file": ("info.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["updated"] == 1  # 기존 '테스트정본운수' 보강
        assert body["created"] == 1  # 신규 '신규정본운수'

        db.expire_all()
        got = db.get(models.Client, cid)
        assert got.biz_reg_no == "221-81-00682"  # 사업자번호 보강됨
        assert got.corp_reg_no == "140111-0000105"
        assert got.ceo_name == "이동진"
        assert got.region == "강원"  # 조합→지역 갱신
        # 신규 건 생성 확인
        newc = db.query(models.Client).filter(models.Client.company_name == "신규정본운수").first()
        assert newc is not None and newc.biz_reg_no == "111-11-11111"
    finally:
        db.query(models.Client).filter(
            models.Client.company_name.in_(["테스트정본운수", "신규정본운수"])
        ).delete(synchronize_session=False)
        db.commit()
        db.close()


_REAL = "/Users/ssh/Documents/Develope/hooxi-cms/Docs/고객사/운수사 관련 정보_260820.xlsx"


@pytest.mark.skipif(not os.path.exists(_REAL), reason="실제 정보 파일 없음(CI 스킵)")
def test_real_transport_info_all_valid(client):
    db = models.SessionLocal()
    try:
        res = excel_import.parse_and_validate(db, "transport_info", open(_REAL, "rb").read())
        assert len([r for r in res.rows if r.errors]) == 0
        assert len(res.valid_rows) == 617
    finally:
        db.close()
