"""충전 인프라(차고지·충전기·계) — 파서 forward-fill·권역교체 적재·요약(D3)."""

import io

import openpyxl

import models
from services import charging_infra_import as cii

API = "/api/v1/charging-infra"


def _xlsx():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "충전기 제원 및 AC전력량계"
    ws.append(["연번", "차고지 주소", "운수사", "연번", "충전기 제원", None, "연번", "AC전력량계", None])
    ws.append([None, None, None, None, "제조번호", "제조년월", None, "제조번호", "제조년월"])
    # 차고지1(강원) — 충전기 2, 계 1 (2행: 첫행 차고지정보 + 둘째행 forward-fill)
    ws.append([1, "강원특별자치도 강릉시 강변로 1", "동진버스", 1, "CHG001", "2020.08", 1, "MTR001", "2022.06"])
    ws.append([None, None, None, 2, "CHG002", "2023.09", None, None, None])
    # 차고지2(제주)
    ws.append([2, "제주특별자치도 제주시 용담이동 1", "삼영교통", 1, "CHG003", "2019.12", 1, "MTR002", "2020.06"])
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


def test_parser_forward_fill():
    facs = cii.parse_charging_infra(_xlsx())
    assert len(facs) == 2
    f0 = next(f for f in facs if f["operator_name"] == "동진버스")
    assert f0["region"] == "강원"
    assert len(f0["chargers"]) == 2  # forward-fill로 둘째 충전기 흡수
    assert len(f0["meters"]) == 1


def test_import_summary_and_region_replace(client, staff_headers):
    db = models.SessionLocal()
    try:
        for m in (models.Charger, models.AcPowerMeter, models.ChargingFacility):
            db.query(m).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()
    files = {"file": ("chg.xlsx", _xlsx(),
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = client.post(API + "/import", headers=staff_headers, files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["facilities"] == 2 and body["chargers"] == 3 and body["meters"] == 2

    summ = client.get(API + "/summary", headers=staff_headers).json()
    assert summ["facilities"] == 2 and summ["chargers"] == 3

    # 재업로드(같은 권역) 멱등 — 여전히 2 차고지
    client.post(API + "/import", headers=staff_headers,
                files={"file": ("chg.xlsx", _xlsx(), files["file"][2])})
    summ2 = client.get(API + "/summary", headers=staff_headers).json()
    assert summ2["facilities"] == 2

    lst = client.get(API, headers=staff_headers, params={"region": "강원"}).json()
    assert lst["total"] == 1 and lst["items"][0]["charger_count"] == 2

    db = models.SessionLocal()
    try:
        for m in (models.Charger, models.AcPowerMeter, models.ChargingFacility):
            db.query(m).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_requires_auth(client):
    assert client.get(API).status_code == 401
