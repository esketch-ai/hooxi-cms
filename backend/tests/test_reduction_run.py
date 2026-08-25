"""차량별 산정 입력 upsert + 전 차량 계산 연결(D5)."""

import io

import openpyxl

import models

IMPORT = "/api/v1/calc-inputs/import"
RUN = "/api/v1/reduction-run"


def _xlsx(rows):
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["차량번호", "업체명", "권역", "연료", "연평균 주행거리(베이스라인)",
               "연평균 연료사용량", "연평균 주행거리(사업)", "연평균 충전량",
               "전기차등록연도", "민간투자비율"])
    for r in rows:
        ws.append(r)
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


def test_import_upsert_and_run(client, staff_headers):
    db = models.SessionLocal()
    try:
        db.query(models.VehicleCalcInput).delete(synchronize_session=False); db.commit()
    finally:
        db.close()
    # 강원 검증 차량(엔진 회귀와 동일 입력) + 민간비율 0.4
    rows = [["강원70자1088", "춘천시민버스", "강원", "CNG",
             73218.33636363636, 48344.80124954544, 69399.53571428571, 83636.09999999999, 2023, 0.4]]
    f = {"file": ("calc.xlsx", _xlsx(rows), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = client.post(IMPORT, headers=staff_headers, files=f)
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 1

    # 재업로드 → 갱신(중복체크)
    r2 = client.post(IMPORT, headers=staff_headers, files={"file": ("calc.xlsx", _xlsx(rows), f["file"][2])})
    assert r2.json()["updated"] == 1 and r2.json()["created"] == 0

    run = client.get(RUN, headers=staff_headers).json()
    assert run["computed"] == 1
    item = run["items"][0]
    assert item["usage_year"] == 2
    assert abs(item["project_emission"] - 38.423) < 1e-3
    # 총감축 > 0, 민간반영 = 총 × 0.4
    assert item["total_reduction"] > 0
    assert abs(item["adjusted_total"] - item["total_reduction"] * 0.4) < 1e-2

    db = models.SessionLocal()
    try:
        db.query(models.VehicleCalcInput).delete(synchronize_session=False); db.commit()
    finally:
        db.close()


def test_skip_on_missing_input(client, staff_headers):
    db = models.SessionLocal()
    try:
        db.query(models.VehicleCalcInput).delete(synchronize_session=False)
        db.add(models.VehicleCalcInput(vehicle_no="불완전1", fuel="경유", baseline_distance=1000))
        db.commit()
    finally:
        db.close()
    run = client.get(RUN, headers=staff_headers).json()
    assert run["skipped"] >= 1
    db = models.SessionLocal()
    try:
        db.query(models.VehicleCalcInput).delete(synchronize_session=False); db.commit()
    finally:
        db.close()


def test_requires_auth(client):
    assert client.get("/api/v1/calc-inputs").status_code == 401
