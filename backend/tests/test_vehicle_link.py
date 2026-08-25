"""차량 정규 링크 백필(정합 3) — VIN 우선, 차량번호+EV 폴백, 모호 감지."""

import models

API = "/api/v1/vehicles/link-backfill"


def _clean():
    db = models.SessionLocal()
    try:
        for M in (models.ReductionRegistry, models.VehicleCalcInput, models.ClientVehicle):
            db.query(M).filter(M.vehicle_no.in_(["강원70자L1", "강원70자L2"])).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_link_vin_and_fuel(client, staff_headers):
    _clean()
    db = models.SessionLocal()
    try:
        c = models.Client(client_type="TRANSPORT", company_name="링크운수", region="강원")
        db.add(c); db.flush()
        # 같은 차량번호에 내연·전기 공존(비유일) — EV/ICE 구분 필요
        ev = models.ClientVehicle(client_id=c.client_id, vehicle_no="강원70자L1", fuel="전기",
                                  chassis_no="VIN-EV-1", status="운행")
        ice = models.ClientVehicle(client_id=c.client_id, vehicle_no="강원70자L1", fuel="경유",
                                   chassis_no="VIN-ICE-1", status="운행")
        # 차량번호 유일한 케이스(폴백 매칭)
        ev2 = models.ClientVehicle(client_id=c.client_id, vehicle_no="강원70자L2", fuel="전기",
                                   status="운행")
        db.add_all([ev, ice, ev2]); db.flush()
        # 산정 입력 — project_vin으로 EV 매칭
        db.add(models.VehicleCalcInput(vehicle_no="강원70자L1", project_vin="VIN-EV-1", fuel="경유"))
        # 레지스트리 PROJECT(전기) — VIN 매칭
        db.add(models.ReductionRegistry(role="PROJECT", vehicle_no="강원70자L1", vin="VIN-EV-1", fuel="전기"))
        # 레지스트리 BASELINE(내연) — VIN 매칭
        db.add(models.ReductionRegistry(role="BASELINE", vehicle_no="강원70자L1", vin="VIN-ICE-1", fuel="경유"))
        # 레지스트리 PROJECT VIN 없음 → 차량번호+EV 폴백(유일)
        db.add(models.ReductionRegistry(role="PROJECT", vehicle_no="강원70자L2", fuel="전기"))
        db.commit()
        ev_id, ice_id, ev2_id = ev.vehicle_id, ice.vehicle_id, ev2.vehicle_id
    finally:
        db.close()

    r = client.post(API, headers=staff_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["registry"]["linked"] == 3 and body["registry"]["vin"] == 2
    assert body["calc_input"]["linked"] == 1 and body["calc_input"]["vin"] == 1

    db = models.SessionLocal()
    try:
        ci = db.query(models.VehicleCalcInput).filter_by(vehicle_no="강원70자L1").first()
        assert ci.client_vehicle_id == ev_id  # project_vin=EV VIN → EV 차량
        regs = db.query(models.ReductionRegistry).filter_by(vehicle_no="강원70자L1").all()
        by_role = {x.role: x for x in regs}
        assert by_role["PROJECT"].client_vehicle_id == ev_id   # 전기 VIN
        assert by_role["BASELINE"].client_vehicle_id == ice_id  # 내연 VIN
        reg2 = db.query(models.ReductionRegistry).filter_by(vehicle_no="강원70자L2").first()
        assert reg2.client_vehicle_id == ev2_id  # 폴백(차량번호+EV 유일)
    finally:
        db.close()

    # 멱등 — 재실행 시 이미 링크된 건 skip
    r2 = client.post(API, headers=staff_headers).json()
    assert r2["registry"]["skipped"] == 3 and r2["registry"]["linked"] == 0
    _clean()


def test_ambiguous_no_vin(client, staff_headers):
    """VIN 없고 (차량번호+EV) 후보가 복수면 모호 — 링크 안 함."""
    _clean()
    db = models.SessionLocal()
    try:
        c = models.Client(client_type="TRANSPORT", company_name="모호운수", region="강원")
        db.add(c); db.flush()
        # 같은 (차량번호, EV) 2대 → 모호
        db.add(models.ClientVehicle(client_id=c.client_id, vehicle_no="강원70자L2", fuel="전기", status="운행"))
        db.add(models.ClientVehicle(client_id=c.client_id, vehicle_no="강원70자L2", fuel="전기", status="운행"))
        db.add(models.ReductionRegistry(role="PROJECT", vehicle_no="강원70자L2", fuel="전기"))
        db.commit()
    finally:
        db.close()
    body = client.post(API, headers=staff_headers).json()
    assert body["registry"]["ambiguous"] == 1 and body["registry"]["linked"] == 0
    _clean()


def test_requires_auth(client):
    assert client.post(API).status_code == 401
