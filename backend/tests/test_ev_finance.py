"""전기버스 도입 재무(민간투자비율 근거) — 파서 파생·적재·요약(D2)."""

import io

import openpyxl

import models
from services import ev_finance_import as efi

API = "/api/v1/ev-finance"


def _xlsx():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "강원도"
    ws.append(["기초정보"] + [None] * 19)  # 1행 그룹헤더
    ws.append(["순번", "시/군", "운수사", "차량번호", "차대번호", "연도", "차량등록일", "차종", "연식",
               "자동차 출고가격\n(부가세 제외)", "취득세", "농어촌특별세", "차량가액", "저상버스보조금",
               "전기차보조금", "자부담금", "보조금검증\n(70%이하)", "민간비율", "공공비율", "비고"])
    ws.append([1, "강릉시", "동진버스(주)", "강원72자1319", "VIN1", 2022, "2022-04-19", "시티라이트", 2022,
               350000000, 2100000, 2380000, 354480000, 92000000, 126000000, 132000000,
               0.6228, 0.3722, 0.6278, "비고"])
    # 파생 필요 케이스(자부담·민간비율 빈칸)
    ws.append([2, "강릉시", "동진버스(주)", "강원72자1320", "VIN2", 2022, "2022-05-01", "시티라이트", 2022,
               400000000, 2400000, 2720000, 405120000, 92000000, 126000000, None, None, None, None, None])
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


def test_parser_and_derivation():
    rows = efi.parse_ev_finance(_xlsx())
    assert len(rows) == 2
    r2 = next(r for r in rows if r["vehicle_no"] == "강원72자1320")
    # 자부담 = 출고가 - 보조금합 = 4.0억 - 2.18억 = 1.82억
    assert r2["self_payment"] == 400000000 - 92000000 - 126000000
    # 민간비율 = 자부담/차량가액
    assert abs(r2["private_ratio"] - (r2["self_payment"] / 405120000)) < 1e-6
    assert r2["region"] == "강원"


def test_import_and_summary(client, staff_headers):
    db = models.SessionLocal()
    try:
        db.query(models.EvFinance).delete(synchronize_session=False); db.commit()
    finally:
        db.close()
    files = {"file": ("fin.xlsx", _xlsx(),
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = client.post(API + "/import", headers=staff_headers, files=files)
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 2

    summ = client.get(API + "/summary", headers=staff_headers).json()
    assert summ["count"] == 2
    assert summ["vehicle_value_total"] == 354480000 + 405120000
    assert 0 < summ["avg_private_ratio"] < 1

    lst = client.get(API, headers=staff_headers, params={"search": "강원72자1319"}).json()
    assert lst["total"] == 1 and lst["items"][0]["private_ratio"] is not None

    db = models.SessionLocal()
    try:
        db.query(models.EvFinance).delete(synchronize_session=False); db.commit()
    finally:
        db.close()


def test_requires_auth(client):
    assert client.get(API).status_code == 401
