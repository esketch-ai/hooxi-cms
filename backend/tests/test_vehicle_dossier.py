"""차량 통합 상세(dossier, 개편 P5) — 한 vehicle_no의 전 생애 조립."""

import models

API = "/api/v1/vehicles/{0}/dossier"
VNO = "강원70자D1"


def _clean():
    db = models.SessionLocal()
    try:
        for M in (models.ProjectVehicle, models.ClientVehicle, models.ReductionRegistry,
                  models.VehicleCalcInput, models.ReductionStage, models.VehicleMonthlyLog):
            db.query(M).filter(M.vehicle_no == VNO).delete(synchronize_session=False)
        db.query(models.Project).filter(models.Project.project_name == "D사업").delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_dossier_aggregates_all(client, staff_headers):
    _clean()
    db = models.SessionLocal()
    try:
        c = models.Client(client_type="TRANSPORT", company_name="도시에운수", region="강원")
        db.add(c); db.flush()
        db.add(models.ClientVehicle(client_id=c.client_id, vehicle_no=VNO, fuel="전기",
                                    status="운행", model_name="일렉시티"))
        p = models.Project(project_name="D사업", project_status="모니터링")
        db.add(p); db.flush()
        db.add(models.ProjectVehicle(project_id=p.project_id, client_id=c.client_id, vehicle_no=VNO,
                                     introduction_type="대체도입", total_reduction=200))
        db.add(models.ReductionRegistry(role="PROJECT", vehicle_no=VNO, vin="EV-D"))
        db.add(models.VehicleCalcInput(vehicle_no=VNO, fuel="CNG", project_distance=70000))
        db.add(models.ReductionStage(vehicle_no=VNO, stage="MONITORING", total_reduction=190))
        db.add(models.VehicleMonthlyLog(vehicle_no=VNO, year_month="2025-05", source="INTEGRATED",
                                        distance_km=6000, charge_kwh=7000))
        db.commit()
    finally:
        db.close()

    r = client.get(API.format(VNO), headers=staff_headers)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["found"] is True
    assert len(d["owned"]) == 1 and d["owned"][0]["model_name"] == "일렉시티"
    assert len(d["participations"]) == 1 and d["participations"][0]["project_name"] == "D사업"
    assert len(d["registry"]) == 1 and d["registry"][0]["vin"] == "EV-D"
    assert d["calc_input"]["fuel"] == "CNG"
    assert d["stages"]["MONITORING"]["total_reduction"] == 190.0
    assert d["log_summary"]["month_count"] == 1 and d["log_summary"]["total_charge"] == 7000.0
    _clean()


def test_dossier_not_found(client, staff_headers):
    r = client.get(API.format("없는차량999"), headers=staff_headers)
    assert r.status_code == 200
    assert r.json()["found"] is False


def test_requires_auth(client):
    assert client.get(API.format(VNO)).status_code == 401
