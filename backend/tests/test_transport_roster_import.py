"""운수사 명부(민원대응 회원명부) 일괄등록 — 변환·파싱·커밋.

합성 엑셀로 회사명 정제·전화/팩스 형식·면허일자·다중번호를 검증(실파일 비의존).
실파일이 있으면 전량 파싱만 추가 확인(skipif).
"""

import io
import os

import openpyxl
import pytest

import models
from services import excel_import

ROSTER_HEADERS = [
    "순번", "조합", "회사명", "대표자", "전 화", "FAX", "업체 주소",
    "시내", "농어촌", "시외", "계", "면허일자", "시/도", "시/군/구",
]


def _build_roster_xlsx(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(ROSTER_HEADERS)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_transform_helpers():
    assert excel_import._tf_company_clean("(주)남성버스") == "남성버스"
    assert excel_import._tf_company_clean("경성여객(주)") == "경성여객"
    assert excel_import._tf_company_clean("주)한국") == "한국"
    assert excel_import._tf_company_clean("한빛운수(유)") == "한빛운수"
    assert excel_import._tf_phone_kr("02)435-5158") == "02-435-5158"
    assert excel_import._tf_phone_kr("041)544-5141,545-3141") == "041-544-5141"  # 첫 번호만
    assert excel_import._tf_license_date_kr("70.10.01") == "1970-10-01"
    assert excel_import._tf_license_date_kr("04.07.01") == "2004-07-01"
    with pytest.raises(ValueError):
        excel_import._tf_license_date_kr("잘못된값")


def test_roster_parse_and_commit(client, staff_headers):
    data = _build_roster_xlsx([
        [1, "서울", "경성여객(주)", "김종원, 김정환", "02)435-5158", "02)495-0293",
         "서울 중랑구 용마산로 376", 73, None, None, 73, "70.10.01", "서울", "중랑구"],
        [2, "경기", "(주)남성버스", "김영상", "031)461-8415,461-0000", "031)461-8413",
         "경기 군포시 번영로 179", 94, None, None, 94, "04.07.01", "경기", "군포시"],
    ])
    db = models.SessionLocal()
    try:
        db.query(models.Client).filter(models.Client.company_name.in_(["경성여객", "남성버스"])).delete(
            synchronize_session=False
        )
        db.commit()

        # 미리보기(파싱만)
        res = excel_import.parse_and_validate(db, "transport_roster", data)
        assert len(res.valid_rows) == 2 and not [r for r in res.rows if r.errors]
        p0 = res.valid_rows[0].payload
        assert p0.company_name == "경성여객"  # (주) 제거
        assert p0.client_type == "TRANSPORT"  # 기본값
        assert p0.region == "서울"
        assert p0.ceo_name == "김종원, 김정환"  # 다중 대표 유지
        assert p0.ceo_contact_phone == "02-435-5158"
        assert p0.fax == "02-495-0293"
        assert str(p0.license_date) == "1970-10-01"
        assert p0.bus_city == 73
        p1 = res.valid_rows[1].payload
        assert p1.company_name == "남성버스"
        assert p1.ceo_contact_phone == "031-461-8415"  # 다중번호 첫번호

        # 커밋(엔드포인트) — 실제 Client 생성
        r = client.post(
            "/api/v1/imports/transport_roster/commit",
            headers=staff_headers,
            files={"file": ("roster.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert r.status_code == 200, r.text
        assert r.json()["created"] == 2
        got = {c.company_name: c for c in db.query(models.Client).filter(
            models.Client.company_name.in_(["경성여객", "남성버스"])).all()}
        assert set(got) == {"경성여객", "남성버스"}
        assert got["경성여객"].client_type == "TRANSPORT"
        assert got["경성여객"].fax == "02-495-0293"
        assert str(got["경성여객"].license_date) == "1970-10-01"
    finally:
        db.query(models.Client).filter(models.Client.company_name.in_(["경성여객", "남성버스"])).delete(
            synchronize_session=False
        )
        db.commit()
        db.close()


_REAL = "/Users/ssh/Documents/Develope/hooxi-cms/Docs/고객사/(2024.07.08)민원대응용회원명부업체정보.xlsx"


@pytest.mark.skipif(not os.path.exists(_REAL), reason="실제 명부 파일 없음(CI 스킵)")
def test_real_roster_all_valid(client):
    db = models.SessionLocal()
    try:
        res = excel_import.parse_and_validate(db, "transport_roster", open(_REAL, "rb").read())
        errs = [r for r in res.rows if r.errors]
        assert len(errs) == 0, [e.errors for e in errs[:5]]
        assert len(res.valid_rows) == 515
    finally:
        db.close()
