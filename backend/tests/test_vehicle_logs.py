"""차량 월별 운행·충전 로그(D6, P1·P2) — 취합본 WIDE 업로드·정리·집계."""

import io

import openpyxl

import models

IMPORT = "/api/v1/vehicle-logs/import"
CONSOL = "/api/v1/vehicle-logs/consolidate"
AGG = "/api/v1/vehicle-logs/aggregate"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _wide_xlsx():
    """취합본 WIDE: 2개월×(운행일수·운행거리·충전량). SPARSE 차량 포함."""
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["운수사명", "자동차등록번호",
               "2025년05월_운행일수", "2025년05월_운행거리", "2025년05월_충전량",
               "2025년06월_운행일수", "2025년06월_운행거리", "2025년06월_충전량"])
    # 운행+충전 완전
    ws.append(["춘천시민버스", "강원70자1088", 30, 6000, 7000, 31, 6200, 7100])
    # 충전 결여(운행만)
    ws.append(["춘천시민버스", "강원70자2000", 28, 5000, None, 29, 5100, None])
    wb2 = io.BytesIO(); wb.save(wb2); return wb2.getvalue()


def _clean():
    db = models.SessionLocal()
    try:
        db.query(models.VehicleMonthlyLog).delete(synchronize_session=False)
        db.query(models.VehicleCalcInput).delete(synchronize_session=False)
        db.query(models.ReductionRegistry).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_import_consolidate_aggregate(client, staff_headers):
    _clean()
    f = {"file": ("wide.xlsx", _wide_xlsx(), XLSX)}
    r = client.post(IMPORT, headers=staff_headers, files=f)
    assert r.status_code == 200, r.text
    body = r.json()
    # (차량×월) 1행씩: 차량1 2행 + 차량2 2행 = 4행(지표는 컬럼)
    assert body["vehicles"] == 2 and body["months"] == 2
    assert body["created"] == 4 and body["updated"] == 0

    # 재업로드 → upsert(갱신)
    r2 = client.post(IMPORT, headers=staff_headers, files={"file": ("wide.xlsx", _wide_xlsx(), XLSX)})
    assert r2.json()["updated"] == 4 and r2.json()["created"] == 0

    # 자동 정리 뷰 — 충전 결여 차량 감지
    con = client.get(CONSOL, headers=staff_headers).json()
    assert con["vehicle_count"] == 2
    assert con["missing_charge"] == 1 and con["missing_run"] == 0
    by = {v["vehicle_no"]: v for v in con["vehicles"]}
    assert by["강원70자2000"]["has_charge"] is False
    assert by["강원70자1088"]["months"]["2025-05"]["distance_km"] == 6000

    # 집계 → 연평균, 프로그램 차량(레지스트리)만. commit 없이 계산만.
    db = models.SessionLocal()
    try:
        db.add(models.ReductionRegistry(role="PROJECT", vehicle_no="강원70자1088", vin="EV1"))
        db.add(models.VehicleCalcInput(vehicle_no="강원70자1088", fuel="CNG"))
        db.commit()
    finally:
        db.close()
    agg = client.post(AGG + "?commit_project=true", headers=staff_headers).json()
    assert agg["aggregated"] == 1  # 레지스트리 차량만
    assert agg["updated"] == 1
    item = next(i for i in agg["items"] if i["vehicle_no"] == "강원70자1088")
    # (6000+6200)/(30+31)*365 = 12200/61*365 = 73000
    assert abs(item["project_distance"] - 73000.0) < 0.5
    assert abs(item["project_kwh"] - (14100 / 61 * 365)) < 0.5

    # VehicleCalcInput 사업측 갱신 확인
    db = models.SessionLocal()
    try:
        ci = db.query(models.VehicleCalcInput).filter_by(vehicle_no="강원70자1088").first()
        assert ci.project_distance is not None and float(ci.project_distance) > 70000
    finally:
        db.close()
    _clean()


def test_requires_auth(client):
    assert client.get(CONSOL).status_code == 401
